"""Who counts as an administrator.

Three sources, combined:

1. `DEFAULT_ADMIN_IDS` — the built-in owner. Cannot be removed, so the bot can
   never end up with nobody able to administer it.
2. `ADMIN_IDS` in the environment — for provisioning at deploy time.
3. The store — added and removed at runtime with `/admin_qoshish`.

Unlike the channel list, the environment value is *additive* rather than a seed:
an id in `ADMIN_IDS` stays an admin whatever the store says. Removing such an
admin means editing `.env`, which is the point — it is the deploy-time record.
"""

from __future__ import annotations

from app.config import DEFAULT_ADMIN_IDS, get_settings
from app.store.json_store import Store

SETTING_KEY = "extra_admins"


def stored_ids(store: Store) -> list[int]:
    """Admins added at runtime, in the order they were added."""
    raw = store.get_setting(SETTING_KEY) or []
    out: list[int] = []
    for item in raw:
        try:
            out.append(int(item))
        except (TypeError, ValueError):
            continue
    return out


def current_ids(store: Store) -> list[int]:
    """Every administrator id, deduplicated, built-in owner first."""
    combined = list(get_settings().admin_id_list)
    for user_id in stored_ids(store):
        if user_id not in combined:
            combined.append(user_id)
    return combined


def is_admin(store: Store, user_id: int) -> bool:
    return user_id in current_ids(store)


def origin(store: Store, user_id: int) -> str:
    """Where this admin comes from: "owner", "env", or "runtime".

    Determines whether /admin_ochirish can remove them — only "runtime" can.
    """
    if user_id in DEFAULT_ADMIN_IDS:
        return "owner"
    if user_id in get_settings().admin_id_list:
        return "env"
    return "runtime"


async def add(store: Store, user_id: int) -> tuple[list[int], bool]:
    """Add an admin. Returns every admin id and whether anything changed."""
    if user_id in current_ids(store):
        return current_ids(store), False
    await store.set_setting(SETTING_KEY, stored_ids(store) + [user_id])
    return current_ids(store), True


async def remove(store: Store, user_id: int) -> tuple[list[int], bool]:
    """Remove a runtime admin. The built-in owner and ADMIN_IDS are untouched."""
    if user_id in DEFAULT_ADMIN_IDS:
        return current_ids(store), False
    existing = stored_ids(store)
    remaining = [item for item in existing if item != user_id]
    if len(remaining) == len(existing):
        return current_ids(store), False
    await store.set_setting(SETTING_KEY, remaining)
    return current_ids(store), True
