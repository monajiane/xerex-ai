"""Development seed data (M7).

The seeds exist so an administrator can open every screen of the panel and see how it
behaves with real traffic. Two rules keep them honest:

* **Opt-in only** — nothing is seeded automatically, and a production environment
  refuses unless it is asked explicitly with ``--allow-production``.
* **Marked as demo** — every seeded row is recognisable (slug suffix ``-demo``, name
  suffix ``(demo)``, key prefix ``xrx_live_demo``), so demo traffic can never be mistaken
  for a real provider, and ``--reset`` can remove exactly what it created.
"""

from app.seeds.demo import DEMO_SUFFIX, reset_demo, seed_demo

__all__ = ["DEMO_SUFFIX", "seed_demo", "reset_demo"]
