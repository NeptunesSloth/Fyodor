"""Fyodor — a personal restock + auto-checkout assistant.

Design principles baked into this package:

* One account. Checkout runs in a single persistent browser profile that you
  log in to yourself. There is no multi-account / rotation machinery.
* Respect the limit. Quantities are always clamped to the per-customer cap.
* No circumvention. If a store presents a CAPTCHA, queue, or other human
  challenge, Fyodor stops and hands control back to you.
* Be polite. Polling has a hard minimum interval and added jitter.
"""

__version__ = "0.1.0"
