import asyncio
import websockets
from http import HTTPStatus

clients = {}

async def handler(websocket):
    try:
        # Primul mesaj primit indică tipul clientului: "PC" sau "PHONE"
        client_type = await websocket.recv()
        clients[client_type] = websocket
        print(f"Conectat: {client_type}")

        async for message in websocket:
            if client_type == "PHONE" and "PC" in clients:
                await clients["PC"].send(message)
                
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        for key, val in list(clients.items()):
            if val == websocket:
                del clients[key]

# Funcție care răspunde cererilor HTTP normale (browser / Render health check)
async def process_request(connection, request):
    if "Upgrade" not in request.headers or request.headers["Upgrade"].lower() != "websocket":
        return connection.respond(HTTPStatus.OK, "Serverul WebSocket este ONLINE!\n")

async def main():
    async with websockets.serve(
        handler, 
        "0.0.0.0", 
        8080, 
        process_request=process_request
    ):
        print("Serverul WebSocket a pornit pe portul 8080...")
        await asyncio.Event().wait()

if __name__ == "__main__":
    asyncio.run(main())
