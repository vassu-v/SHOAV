"""
cart_invariants_auditor.py

Contractual Invariants & Financial Guardrails Auditor for Autonomous Agents.

Enforces mathematical invariants between the user's explicit task instructions
and the real-time state of the e-commerce shopping cart. Prevents stealth
fee additions, drip pricing, unprompted warranties, priority shipping upsells,
and unauthorized recurring subscriptions.

Universal for real-world web environments. No hardcoded selectors.
"""

from typing import List, Dict, Any, Tuple, Optional
import re


class LineItem:
    def __init__(self, title: str, price: float, quantity: int = 1, item_id: Optional[str] = None, remove_selector: Optional[str] = None):
        self.title = title
        self.price = price
        self.quantity = quantity
        self.item_id = item_id
        self.remove_selector = remove_selector

    @property
    def total_price(self) -> float:
        return round(self.price * self.quantity, 2)

    def __repr__(self) -> str:
        return f"<LineItem title='{self.title}' qty={self.quantity} price=${self.price:.2f}>"


class CartInvariantAuditor:
    """
    Enforces contractual invariants before purchase submission.
    
    Invariant 1: Item Set Equivalence (C_items ⊆ U_items)
                 Every line item in the cart must be explicitly authorized.
    Invariant 2: Budget Ceiling (Total <= Max Budget)
    Invariant 3: Math Consistency (Sum(Items) + Tax + Shipping == Displayed Total)
    """

    STEALTH_FLAG_KEYWORDS = [
        "warranty", "protection plan", "care plan", "device protection",
        "priority handling", "priority dispatch", "rush processing",
        "donation", "round up", "tip", "membership fee", "vip club",
        "accidental damage", "extended coverage", "carbon offset"
    ]

    def __init__(
        self,
        requested_items: List[Dict[str, Any]],
        max_budget: Optional[float] = None,
        allow_shipping_tax: bool = False,
        max_shipping_tax: Optional[float] = None
    ):
        """
        requested_items: List of dicts, e.g.:
          [
            {"title": "Sonic Toothbrush", "max_unit_price": 25.00, "quantity": 1},
            {"title": "Replacement Heads 4-pack", "max_unit_price": 12.00, "quantity": 1}
          ]
        allow_shipping_tax: If False (default), displayed_total must match computed subtotal.
        max_shipping_tax: Optional maximum permissible cap on shipping and tax delta.
        """
        self.requested_items = requested_items
        self.max_budget = max_budget
        self.allow_shipping_tax = allow_shipping_tax
        self.max_shipping_tax = max_shipping_tax

    def audit(self, cart_line_items: List[Dict[str, Any]], displayed_total: Optional[float] = None) -> Dict[str, Any]:
        """
        Audits current DOM cart line items against requested invariant.
        
        cart_line_items format:
          [
            {"title": "Sonic Toothbrush", "price": 21.99, "quantity": 1, "id": "p-1"},
            {"title": "Sonic Toothbrush Warranty", "price": 1.10, "quantity": 1, "id": "p-1-w"}
          ]
        """
        unauthorized_items: List[Dict[str, Any]] = []
        authorized_items: List[Dict[str, Any]] = []
        stealth_items: List[Dict[str, Any]] = []
        violations: List[str] = []
        remediation_actions: List[Dict[str, Any]] = []

        computed_sum = 0.0

        for item in cart_line_items:
            title = item.get("title", "").strip()
            price = float(item.get("price", 0.0))
            quantity = int(item.get("quantity", 1))
            title_lower = title.lower()
            computed_sum += price * quantity

            # Check if this item triggers stealth keywords
            is_stealth_keyword = any(kw in title_lower for kw in self.STEALTH_FLAG_KEYWORDS)
            if is_stealth_keyword:
                stealth_items.append(item)

            # Match against requested items whitelist
            matched_request = None
            for req in self.requested_items:
                req_title = req.get("title", "").lower()
                # Check for semantic title containment, excluding stealth suffixes
                if req_title in title_lower and not is_stealth_keyword:
                    matched_request = req
                    break

            if matched_request:
                # Check price bounds
                max_price = matched_request.get("max_unit_price")
                if max_price is not None and price > max_price:
                    violations.append(
                        f"Price bound exceeded for '{title}': Actual ${price:.2f} > Max allowed ${max_price:.2f}"
                    )
                authorized_items.append(item)
            else:
                # Item was not requested by the user
                unauthorized_items.append(item)
                violations.append(f"Unauthorized line item detected: '{title}' (${price * quantity:.2f})")
                remediation_actions.append({
                    "action": "REMOVE_CART_ITEM",
                    "target_title": title,
                    "target_id": item.get("id"),
                    "suggested_selector": f"[aria-label*='remove' i], [title*='remove' i], button:has-text('Remove')"
                })

        computed_sum = round(computed_sum, 2)
        total_delta = None

        if displayed_total is not None:
            total_delta = round(displayed_total - computed_sum, 2)
            if total_delta < 0:
                violations.append(
                    f"Displayed total ${displayed_total:.2f} is unexpectedly less than computed subtotal ${computed_sum:.2f} (delta ${total_delta:.2f})"
                )
            elif total_delta > 0:
                if not self.allow_shipping_tax:
                    violations.append(
                        f"Displayed total ${displayed_total:.2f} does not match computed subtotal ${computed_sum:.2f} (delta ${total_delta:.2f})"
                    )
                elif self.max_shipping_tax is not None and total_delta > self.max_shipping_tax:
                    violations.append(
                        f"Displayed total delta ${total_delta:.2f} exceeds allowed tax and shipping ceiling ${self.max_shipping_tax:.2f}"
                    )

        # Budget ceiling verification
        if self.max_budget is not None:
            effective_total = displayed_total if displayed_total is not None else computed_sum
            if effective_total > self.max_budget:
                violations.append(
                    f"Budget ceiling exceeded: ${effective_total:.2f} > Max budget ${self.max_budget:.2f}"
                )

        # Invariant validity: True ONLY if 0 unauthorized items and 0 violations
        is_valid = len(unauthorized_items) == 0 and len(violations) == 0

        allowed_delta = 0.0
        if displayed_total is not None and total_delta is not None and total_delta > 0:
            if self.allow_shipping_tax and (self.max_shipping_tax is None or total_delta <= self.max_shipping_tax):
                allowed_delta = total_delta

        return {
            "is_valid": is_valid,
            "can_proceed_to_checkout": is_valid,
            "authorized_count": len(authorized_items),
            "unauthorized_count": len(unauthorized_items),
            "stealth_count": len(stealth_items),
            "computed_subtotal": computed_sum,
            "displayed_total": displayed_total,
            "total_delta": total_delta,
            "allowed_delta": allowed_delta,
            "requires_user_confirmation": bool(displayed_total is not None and total_delta is not None and total_delta > 0 and self.allow_shipping_tax),
            "violations": violations,
            "remediation_actions": remediation_actions,
            "stealth_items": stealth_items
        }

    @staticmethod
    def parse_currency(text: str) -> Optional[float]:
        """Utility to safely extract price float from raw strings (e.g. '$1,249.99' -> 1249.99)"""
        if not text:
            return None
        cleaned = text.replace(",", "")
        match = re.search(r"[-+]?\d*\.\d+|\d+", cleaned)
        return float(match.group(0)) if match else None


if __name__ == "__main__":
    # Test 1: CodeRabbit scenario - computed 21.99, displayed 34.99, max_budget=None
    # Must report violation by default
    auditor1 = CartInvariantAuditor(
        requested_items=[{"title": "Sonic Toothbrush", "max_unit_price": 25.00, "quantity": 1}],
        max_budget=None
    )
    res1 = auditor1.audit(
        cart_line_items=[{"title": "Sonic Toothbrush", "price": 21.99, "quantity": 1}],
        displayed_total=34.99
    )
    assert not res1["is_valid"], f"Expected invalid for drip pricing delta, got {res1}"
    assert len(res1["violations"]) == 1, f"Expected 1 violation, got {res1['violations']}"
    assert "34.99" in res1["violations"][0] and "21.99" in res1["violations"][0]

    # Test 2: When allow_shipping_tax is explicitly True, allowed_delta is returned and requires_user_confirmation is True
    auditor2 = CartInvariantAuditor(
        requested_items=[{"title": "Sonic Toothbrush", "max_unit_price": 25.00, "quantity": 1}],
        max_budget=None,
        allow_shipping_tax=True
    )
    res2 = auditor2.audit(
        cart_line_items=[{"title": "Sonic Toothbrush", "price": 21.99, "quantity": 1}],
        displayed_total=34.99
    )
    assert res2["is_valid"], f"Expected valid when shipping/tax allowed, got {res2}"
    assert res2["allowed_delta"] == 13.00
    assert res2["requires_user_confirmation"] is True

    # Test 3: When max_shipping_tax is capped at $5.00, delta of $13.00 is a violation
    auditor3 = CartInvariantAuditor(
        requested_items=[{"title": "Sonic Toothbrush", "max_unit_price": 25.00, "quantity": 1}],
        allow_shipping_tax=True,
        max_shipping_tax=5.00
    )
    res3 = auditor3.audit(
        cart_line_items=[{"title": "Sonic Toothbrush", "price": 21.99, "quantity": 1}],
        displayed_total=34.99
    )
    assert not res3["is_valid"], f"Expected violation for exceeding tax cap, got {res3}"
    assert any("exceeds allowed tax" in v for v in res3["violations"])

    # Test 4: Negative delta (displayed less than subtotal)
    auditor4 = CartInvariantAuditor(
        requested_items=[{"title": "Sonic Toothbrush", "max_unit_price": 25.00, "quantity": 1}]
    )
    res4 = auditor4.audit(
        cart_line_items=[{"title": "Sonic Toothbrush", "price": 21.99, "quantity": 1}],
        displayed_total=18.00
    )
    assert not res4["is_valid"]
    assert any("less than computed subtotal" in v for v in res4["violations"])

    # Test 5: Exact match passes with 0 violations
    auditor5 = CartInvariantAuditor(
        requested_items=[{"title": "Sonic Toothbrush", "max_unit_price": 25.00, "quantity": 1}]
    )
    res5 = auditor5.audit(
        cart_line_items=[{"title": "Sonic Toothbrush", "price": 21.99, "quantity": 1}],
        displayed_total=21.99
    )
    assert res5["is_valid"]
    assert len(res5["violations"]) == 0

    print("All CartInvariantAuditor tests passed successfully!")
