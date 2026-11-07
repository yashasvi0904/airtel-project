"""Shared helper: pay an order through the real payment API (sandbox gateway, settles instantly in tests)."""
import uuid


def pay_upi(client, order_id: str, headers: dict, vpa: str = "ravi@okhdfc") -> dict:
    r = client.post(f"/api/orders/{order_id}/payments", json={"method": "upi", "upi": {"flow": "collect", "vpa": vpa}},
                    headers={**headers, "Idempotency-Key": uuid.uuid4().hex})
    assert r.status_code == 201, r.text
    got = client.get(f"/api/payments/{r.json()['id']}", headers=headers).json()  # polling is what settles a pending UPI request
    assert got["status"] == "succeeded", got
    return got
