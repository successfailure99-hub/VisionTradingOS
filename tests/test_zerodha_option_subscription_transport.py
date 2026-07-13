import pytest

from brokers.zerodha.market_data import ZerodhaSubscriptionMode
from brokers.zerodha.option_market_data import ZerodhaTickerOptionSubscriptionTransport, to_kite_mode


class Client:
    def __init__(self, fail=False):
        self.calls = []
        self.fail = fail

    def subscribe(self, tokens):
        self.calls.append(("subscribe", list(tokens)))
        if self.fail:
            raise RuntimeError("subscribe failed")

    def unsubscribe(self, tokens):
        self.calls.append(("unsubscribe", list(tokens)))

    def set_mode(self, mode, tokens):
        self.calls.append(("mode", mode, list(tokens)))


def test_transport_delegates_preserves_order_and_maps_modes():
    client = Client()
    transport = ZerodhaTickerOptionSubscriptionTransport(client)
    assert client.calls == []
    transport.subscribe([3, 1, 2])
    transport.set_mode(to_kite_mode(ZerodhaSubscriptionMode.FULL), [3, 1, 2])
    transport.unsubscribe([1])
    assert client.calls == [("subscribe", [3, 1, 2]), ("mode", "full", [3, 1, 2]), ("unsubscribe", [1])]
    assert to_kite_mode(ZerodhaSubscriptionMode.LTP) == "ltp"
    assert to_kite_mode(ZerodhaSubscriptionMode.QUOTE) == "quote"


@pytest.mark.parametrize("tokens", ([], [1, 1], [True], [0]))
def test_transport_rejects_bad_batches(tokens):
    with pytest.raises((TypeError, ValueError)):
        ZerodhaTickerOptionSubscriptionTransport(Client()).subscribe(tokens)


def test_transport_reraises_and_does_not_connect_or_set_callbacks():
    client = Client(fail=True)
    with pytest.raises(RuntimeError):
        ZerodhaTickerOptionSubscriptionTransport(client).subscribe([1])
    assert not hasattr(ZerodhaTickerOptionSubscriptionTransport(client), "connect")
    assert not hasattr(ZerodhaTickerOptionSubscriptionTransport(client), "set_callbacks")
