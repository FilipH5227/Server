import os
import json
from aiohttp import web, WSMsgType
from database import register_user, authenticate_user

# Structure: { "USERNAME": { "pc": ws_pc, "phone": ws_phone } }
sessions = {}

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    current_user = None
    role = None

    try:
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                data = json.loads(msg.data)
                msg_type = data.get("type")

                # --- REGISTRATION / LOGIN ---
                if msg_type == "REGISTER":
                    success, message = register_user(data.get("username"), data.get("password"))
                    await ws.send_json({"type": "AUTH_RESPONSE", "success": success, "message": message})

                elif msg_type == "LOGIN":
                    username = data.get("username")
                    password = data.get("password")
                    role = data.get("role")  # "PC" or "PHONE"

                    success, message = authenticate_user(username, password)
                    if success:
                        current_user = username
                        if current_user not in sessions:
                            sessions[current_user] = {"pc": None, "phone": None}

                        if role == "PC":
                            sessions[current_user]["pc"] = ws
                            if sessions[current_user]["phone"]:
                                await sessions[current_user]["phone"].send_json({"type": "PC_STATUS", "connected": True})
                        elif role == "PHONE":
                            sessions[current_user]["phone"] = ws

                        await ws.send_json({"type": "AUTH_RESPONSE", "success": True, "message": "Authenticated!"})
                        
                        # Send current connection status to mobile
                        pc_online = sessions[current_user]["pc"] is not None
                        await ws.send_json({"type": "PC_STATUS", "connected": pc_online})
                    else:
                        await ws.send_json({"type": "AUTH_RESPONSE", "success": False, "message": message})

                # --- COMMANDS & STREAM RELAY (ACCOUNT ISOLATED) ---
                elif msg_type in ["stream", "command"]:
                    if current_user and current_user in sessions:
                        user_session = sessions[current_user]
                        if role == "PC" and user_session["phone"]:
                            await user_session["phone"].send_str(msg.data)
                        elif role == "PHONE" and user_session["pc"]:
                            await user_session["pc"].send_str(msg.data)

    finally:
        if current_user and current_user in sessions:
            if role == "PC":
                sessions[current_user]["pc"] = None
                if sessions[current_user]["phone"]:
                    await sessions[current_user]["phone"].send_json({"type": "PC_STATUS", "connected": False})
            elif role == "PHONE":
                sessions[current_user]["phone"] = None

    return ws

async def http_handler(request):
    return web.Response(text="DeskGuard Cloud Server Online")

app = web.Application()
app.router.add_get('/', http_handler)
app.router.add_get('/ws', websocket_handler)

if __name__ == '__main__':
    port = int(os.environ.get("PORT", 8080))
    web.run_app(app, host='0.0.0.0', port=port)
