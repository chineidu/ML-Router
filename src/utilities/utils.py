import msgspec

ENCODER = msgspec.json.Encoder()
DECODER = msgspec.json.Decoder()


def calculate_latency(
    old_latency: float | None, current_latency: float, alpha: float = 0.2
) -> float:
    """
    Calculates the exponentially weighted moving average latency (EWMA).
    Using EWMA helps to smooth out short-term fluctuations and highlight
    longer-term trends in latency.
    """
    if not old_latency:
        return round(current_latency, 2)

    new_latency = (alpha * current_latency) + ((1 - alpha) * old_latency)
    return round(new_latency, 2)
