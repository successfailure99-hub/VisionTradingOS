"""
====================================================
Vision Trading OS
Zerodha Live Data Engine
====================================================
"""

from kiteconnect import KiteConnect, KiteTicker


class ZerodhaDataEngine:

    def __init__(self, api_key: str, access_token: str):

        self.api_key = api_key
        self.access_token = access_token

        self.kite = KiteConnect(api_key=api_key)
        self.kite.set_access_token(access_token)

        self.ticker = KiteTicker(api_key, access_token)

        self.connected = False

        self.market_data = {}

    def connect(self):

        self.ticker.on_connect = self.on_connect
        self.ticker.on_ticks = self.on_ticks
        self.ticker.on_close = self.on_close

        self.ticker.connect(threaded=True)

    def on_connect(self, ws, response):

        print("Connected to Zerodha")

        self.connected = True

    def on_ticks(self, ws, ticks):

        for tick in ticks:

            self.market_data[tick["instrument_token"]] = tick

    def on_close(self, ws, code, reason):

        print("Connection Closed")

        self.connected = False

    def get_market_data(self):

        return self.market_data