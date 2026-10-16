"""Deterministic reservation rule example; no service or AI backend."""
def reserve(bookings, slot, person) -> dict[str, str]:
    if not slot or not person:
        raise ValueError('slot and person required')
    if slot in bookings:
        if bookings[slot] == person:
            return dict(bookings)  # same request is idempotent
        raise ValueError('slot already booked')
    return {**bookings, slot: person}
