import json
from channels.generic.websocket import AsyncWebsocketConsumer

class StatsConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        self.group_name = "stats"

        # Add this connection to "stats" group
        await self.channel_layer.group_add(self.group_name, self.channel_name)

        # Accept WebSocket connection
        await self.accept()

    async def disconnect(self, close_code):
        # Remove this connection from "stats" group
        await self.channel_layer.group_discard(self.group_name, self.channel_name)

    async def stat_update(self, event):
        """
        Called when EventStat is updated and we broadcast a message:
        channel_layer.group_send("stats", {"type": "stat.update", "data": {...}})
        """
        await self.send(text_data=json.dumps(event["data"]))
