---
name: frontend_ux
domain: ui_ux
polarity: MODE_A_HOLISTIC_ARCHITECT
description: High-craft UI/UX design system, WCAG 2.2 AA contrast math, semantic typography scales, and zero-slop interactive rendering.
---
# Frontend & UX Engineering Playbook (`cod.ai` Mode A)

## 1. Visual & Interactive Standards
- **WCAG >= 4.5:1 Relative Luminance Contrast**: All text and interactive controls must satisfy strict WCAG contrast formulas against their immediate surface background.
- **Deterministic Layout Grid**: Use CSS Grid and Flexbox with explicit gap tokens (`4px`, `8px`, `16px`, `24px`, `32px`); never hardcode fragile pixel offsets that clip or overflow.
- **Complete State Coverage**: Every interactive component must implement `idle`, `loading`, `empty`, `error`, and `populated` states without stubbed handlers.
