import asyncio
import json
import os

import aiohttp
import aiohttp_jinja2
import jinja2
from aiohttp import web


def init_webserver(bundle_dir, config, play_manager, server_name):
    web_dir = os.path.join(bundle_dir, "server", "web")

    max_player_name_length = config["webserver"].getint("max_player_name_length")

    app = web.Application()
    aiohttp_jinja2.setup(app, loader=jinja2.FileSystemLoader(web_dir))

    # Store active WebSocket connections
    app["websockets"] = set()
    players_by_connection = {}

    @aiohttp_jinja2.template("player.html")
    async def index(request):
        """
        Returns:
            dict: Video configuration and stream settings to be rendered by the template.
        """
        stream_config = {
            stream: f"http://{request.host.split(':')[0]}:1984/stream.html?src={stream}"
            for stream, device in config.items("video_streams")
            if device
        }
        return {
            "enable_video": config["webserver"].getboolean("enable_video"),
            "video_streams": stream_config,
            "max_player_name_length": max_player_name_length,
            "motd": config["webserver"]["motd"].strip('"'),
            "ws_timeout": config["webserver"]["ws_timeout"],
        }

    async def favicon(request):
        """
        Returns:
            Response: The favicon.ico file from the web directory.
        """
        return web.FileResponse(os.path.join(web_dir, "favicon.ico"))

    async def script(request):
        """
        Returns:
            Response: The player.js file from the web directory.
        """
        return web.FileResponse(os.path.join(web_dir, "player.js"))

    async def stylesheet(request):
        """
        Returns:
            Response: The style.css file from the web directory.
        """
        return web.FileResponse(os.path.join(web_dir, "player.css"))

    async def broadcast_state(event, data):
        """
        Broadcast the player list to all clients.
        """
        payload = json.dumps({event: data})
        for websocket in list(app["websockets"]):
            try:
                await websocket.send_str(payload)
            except Exception:
                app["websockets"].remove(websocket)

    async def connect_player(session_id, websocket, data):
        """
        Assigns a player to a WebSocket when requested by the client.
        """
        player = players_by_connection.get(session_id)
        if player is None:
            player = play_manager.player_join()
            if player is None:
                await websocket.send_str(json.dumps({"error": "no_player_slots"}))
                return
            players_by_connection[session_id] = player

        player_name = data.get("player_name")
        if isinstance(player_name, str) and len(player_name) <= max_player_name_length:
            player.player_name = player_name

        await websocket.send_str(json.dumps({"player_id": player.player_id}))
        await broadcast_state("players", play_manager.get_player_info())

    async def release_player(session_id):
        """
        Releases the player assigned to a WebSocket, if any.
        """
        player = players_by_connection.pop(session_id, None)
        if player is not None:
            play_manager.player_quit(player.player_id)
            await broadcast_state("players", play_manager.get_player_info())

    async def handle_input(session_id, websocket, data):
        """
        Processes a connection command, player update, or control input.

        Args:
            session_id (str): Session identifier
            data (dict): Player data containing:
                - 'command' (str): Optional command, such as 'CONNECT' or 'RELEASE'
                - 'player_name' (str): Optional display name
                - 'button' (str): Control button identifier
                - 'pressed' (bool): Control button state
        """
        if data.get("command") == "CONNECT":
            await connect_player(session_id, websocket, data)
            return

        if data.get("command") == "RELEASE":
            await release_player(session_id)
            return

        if data.get("button") == "UPDATE":
            player = players_by_connection.get(session_id)
            if player:
                player_name = data.get("player_name")
                if len(player_name) <= max_player_name_length:
                    player.player_name = player_name
                await broadcast_state("players", play_manager.get_player_info())
            return

        player = players_by_connection.get(session_id)
        if player is None:
            return

        player_name = data.get("player_name")
        if len(player_name) <= max_player_name_length:
            player.player_name = player_name

        play_manager.handle_input(player, data)
        await broadcast_state("players", play_manager.get_player_info())

    async def handle_websocket(request):
        """
        Handles player connections, disconnections, and player input.
        """
        websocket = web.WebSocketResponse()
        await websocket.prepare(request)

        session_id = str(id(websocket))
        request.app["websockets"].add(websocket)
        play_manager.logger.debug(f"Session ID {session_id} WebSocket connection opened")

        try:
            async for msg in websocket:
                if msg.type == aiohttp.WSMsgType.TEXT:
                    data = json.loads(msg.data)
                    await handle_input(session_id, websocket, data)
                elif msg.type == aiohttp.WSMsgType.ERROR:
                    print(f"WebSocket connection closed with exception {websocket.exception()}")
        # Handle interrupts
        except asyncio.CancelledError:
            pass
        finally:
            request.app["websockets"].discard(websocket)
            play_manager.logger.debug(f"Session ID {session_id} WebSocket connection closed")
            await release_player(session_id)

        return websocket

    app.router.add_get("/", index)
    app.router.add_get("/favicon.ico", favicon)
    app.router.add_get("/player.js", script)
    app.router.add_get("/player.css", stylesheet)
    app.router.add_get("/ws", handle_websocket)

    return app
