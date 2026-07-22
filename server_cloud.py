import asyncio
import websockets

# Stocăm conexiunile active
clients = {}

async def handler(websocket):
    try:
        # Primul mesaj primit indică tipul clientului: "PC" sau "PHONE"
        client_type = await websocket.recv()
        clients[client_type] = websocket
        print(f"Conectat: {client_type}")

        async for message in websocket:
            # Ce vine de la telefon trimitem la PC
            if client_type == "PHONE" and "PC" in clients:
                await clients["PC"].send(message)
                
    except websockets.exceptions.ConnectionClosed:
        pass
    finally:
        # Curățăm conexiunea la deconectare
        for key, val in list(clients.items()):
            if val == websocket:
                del clients[key]

async def main():
    # Pornim serverul pe portul 8080
    async with websockets.serve(handler, "0.0.0.0", 8080):
        await asyncio.future()

if __name__ == "__main__":
    asyncio.run(main())