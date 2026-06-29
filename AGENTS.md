# Soulmeet / Aini Frontend Rules

## Product Style
This is an anime companion AI product, not an enterprise dashboard.
UI should feel soft, emotional, premium, dreamy, and clean.

Use:
- pastel purple / pink / white
- glassmorphism
- rounded cards
- soft shadows
- clear spacing
- elegant Chinese UI text

Avoid:
- dense admin dashboard layout
- harsh borders
- loud saturated colors
- cluttered cards
- hidden buttons
- broken mobile layout

## Engineering Rules
- Do not rewrite entire pages unless required.
- Prefer small component extraction.
- Preserve existing chat, voice, interruption, weather, sidebar, and input behavior.
- Use existing styling system and dependencies.
- Do not add large UI libraries.
- Keep desktop and mobile responsive.

## Verification
After frontend changes, run the existing type-check/build command when possible.
Report any existing unrelated build errors separately.

## Chat Layout Rules

This product is an anime companion AI chat app, not an enterprise dashboard.

For chat layout changes:
- Keep the UI soft, dreamy, rounded, and glassmorphic.
- Preserve the existing Aini character, voice controls, weather controls, sidebar, input box, and conversation detail panel.
- Do not rewrite the entire chat page unless absolutely necessary.
- Main chat area should use large rounded corners.
- Side panels should support clear collapse and expand states.
- Collapse buttons must always be visible.
- Mobile layout must not overflow horizontally.
- Do not add annotation text from design references into the real UI.
