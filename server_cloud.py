import asyncio
from aiohttp import web, WSMsgType

# Stocăm conexiunile active
clients = {}

async def websocket_handler(request):
    ws = web.WebSocketResponse()
    await ws.prepare(request)

    client_type = None
    try:
        # Primul mesaj primit indică tipul clientului ("PC" sau "PHONE")
        async for msg in ws:
            if msg.type == WSMsgType.TEXT:
                if client_type is None:
                    client_type = msg.data.strip()
                    clients[client_type] = ws
                    print(f"Conectat: {client_type}")
                else:
                    # Dacă telefonul trimite ceva, redirecționăm către PC
                    if client_type == "PHONE" and "PC" in clients:
                        await clients["PC"].send_str(msg.data)
            elif msg.type == WSMsgType.ERROR:
                print(f"Excepție WebSocket: {ws.exception()}")
    finally:
        if client_type and client_type in clients:
            del clients[client_type]
            print(f"Deconectat: {client_type}")

    return ws

async def http_handler(request):
    # Răspuns curat pentru orice cerere HTTP simplă din browser sau Render Health Check
    return web.Response(text="Serverul WebSocket este ONLINE!")

def make_app():
    app = web.Application()
    app.router.add_get('/', http_handler)
    app.router.add_get('/ws', websocket_handler)
    return app

if __name__ == '__main__':
    app = make_app()
    web.run_app(app, host='0.0.0.0', port=8080)
