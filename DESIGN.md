---
name: Pozzo Launcher
description: Libreria universale per ROM di console e giochi PC
colors:
  primary: "#6366f1"
  primary-hover: "#4f46e5"
  accent: "#38bdf8"
  bg-dark: "#0b0f19"
  card-dark: "#131b2e"
  border-dark: "#1e293b"
  text-main: "#f8fafc"
  text-muted: "#94a3b8"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    fontSize: "3.5rem"
    fontWeight: 800
    lineHeight: 1.15
    letterSpacing: "-0.02em"
  heading:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    fontSize: "2rem"
    fontWeight: 700
    lineHeight: 1.25
    letterSpacing: "-0.01em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
    fontSize: "1rem"
    fontWeight: 400
    lineHeight: 1.6
rounded:
  sm: "6px"
  md: "12px"
  lg: "18px"
  full: "9999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "16px"
  lg: "24px"
  xl: "32px"
  xxl: "48px"
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#ffffff"
    rounded: "{rounded.md}"
    padding: "15px 32px"
  button-primary-hover:
    backgroundColor: "{colors.primary-hover}"
---

# Design System: Pozzo Launcher Web & Documentation

## Overview
L'identità visiva del sito ufficiale di Pozzo Launcher su GitHub Pages esprime l'estetica di una moderna libreria da gaming con la chiarezza e l'immediatezza di un prodotto desktop open source rifinito.

## Color Strategy
- **Palette**: Dark Gaming Committed basata su tonalità profonde slate/ardesia (`#0b0f19`, `#131b2e`) con accenti indaco vivace (`#6366f1`) e ciano elettrico (`#38bdf8`).
- **Supporto Light/Dark**: Rispetta il tema di sistema e la preferenza dell'utente tramite il selettore di MkDocs Material.

## Typography & Hierarchy
- **Font Stack**: Tipografia di sistema robusta e pulita con tracking calibrato (-0.02em sui display grandi per dare peso e autorevolezza).
- **Proporzioni**: Nessun gradient text (in linea con le regole di craft), gerarchia garantita da salti di scala e peso precisi.

## Elevation & Depth
- **Ombre e Trasparenze**: Ombre morbide con offset e blur generoso (`0 10px 30px -10px rgba(0, 0, 0, 0.4)`), niente ombre dure ad offset zero.
- **Cornici**: Bordi sottili da 1px a contrasto minimo per separare le sezioni senza creare affollamento visivo.

## Motion & Micro-interactions
- Pulsanti con transizione tattile al passaggio del mouse (`translateY(-2px)` con incremento di sfumatura dell'ombra).
- Schede con micro-hover fluido e badge di raccomandazione automatica del sistema operativo.
