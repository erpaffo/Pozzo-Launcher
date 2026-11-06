"""Endpoint dell'app, un modulo per area. Ogni modulo ha build_router(ctx) -> APIRouter:
ctx contiene le parti costruite da create_app() (cfg, lib, user, launcher, events, job, state, ...)
e le funzioni che un modulo condivide con gli altri (vars(ctx).update). L'ordine conta: chi usa
una funzione di un altro modulo viene dopo."""

from . import boot, images, stores, library, mods, verify, shots, stream, emulators, emulators_extra, gameinfo, system, manual, scan, setup, backups, profiles, profile_settings, sync, saves, integrations, activity, appsettings, pages, top, collart, notify, wishlist, cache_sources, reco, emupresets, downloads, emudetected, controller_profiles, party, i18n  # noqa: F401

ORDER = ['boot', 'images','stores', 'library', 'mods', 'verify', 'shots', 'stream', 'emulators', 'emulators_extra', 'gameinfo', 'system', 'manual', 'scan', 'setup', 'backups', 'profiles', 'profile_settings', 'sync', 'saves', 'integrations', 'activity', 'appsettings', 'pages', 'top', 'collart', 'notify', 'wishlist', 'cache_sources', 'reco', 'emupresets', 'downloads', 'emudetected', 'controller_profiles', 'party', 'i18n']
