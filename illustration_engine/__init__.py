"""Illustration/story database engine — isolated from `bible_engine`.

Grounded, sourced fabulae/tanmesék/történetek tárolására és (később)
kereshetővé tételére szolgáló, önálló modulcsalád. A hymn-adatbázis
architektúráját követi (build-time import réteg + read-only repository
réteg elválasztása, fail-closed validáció), de nem osztozik kódon a
`bible_engine`-nel — csak a stabil `bible_engine.paths` konstansokat
importálja, olvasva.
"""
