# UVE map overlay plan

## CURRENT

The map keeps its own top actions and a lower contextual rail above the global
navigation. Error, empty, and place-feedback surfaces used separate absolute
layers at the same position, so two status cards could compete for the same
viewport when members existed without a visible location.

## TARGET

The visual stack is fixed and predictable:

1. top actions: recenter and explicit location sharing;
2. one status slot: feedback, error, or empty state, in that priority order;
3. optional selected context inside the contextual rail;
4. Integrantes/Lugares navigation;
5. global bottom navigation.

No space is reserved for the selected-context card while there is no selection.
No camera, marker, permission, sharing, API, realtime, or automatic recentering
behavior changes in this slice.

## VALIDATION MATRIX

- 0 locations: one compact empty status, no contextual card.
- 1/N locations: markers remain authoritative; no empty status.
- error: one error surface, with Settings action when required.
- feedback: temporarily replaces other status surfaces.
- selected/unselected members and places: context appears only when selected.
- picker/sheets: preserve their existing geometry and gestures.

