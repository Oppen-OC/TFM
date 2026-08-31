"""Captura y parseo de las fuentes en tiempo real.

La ingesta NO es un stage de DVC y no debe serlo: capturar un stream en vivo
no es idempotente ni reejecutable. El colector corre como proceso aparte y
deja el crudo en `raw/`; el pipeline reproducible empieza ahí.
"""
