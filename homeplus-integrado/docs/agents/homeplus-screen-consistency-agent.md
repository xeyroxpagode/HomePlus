# HomePlus Screen Consistency Agent

Use this role for a cross-module visual alignment slice.

1. Confirm the live HomePlus workspace before editing.
2. Identify whether the screen is Home, a root work module, or a secondary route.
3. Preserve Product Truth, routes, data and permissions.
4. Keep the rich household header exclusive to Home.
5. Ensure every changed root work module owns top safe-area spacing.
6. Use shared theme tokens and primitives before local styles.
7. Align titles, controls and content to the shared screen gutter.
8. Reserve back controls for actual return navigation.
9. Keep tab navigation visually lighter than mode/context selectors.
10. Keep all primary actions reachable without obscuring content under the floating navbar.
11. Preserve 44px touch targets even when visual controls are compact.
12. Test Family People/Map controls below the system inset.
13. Do not replace a screen structure until a reusable mismatch is demonstrated.
14. Run TypeScript and focused lint after each slice.
15. Mark device-only results as NEEDS_DEVICE_QA.
16. Resolve presentation styles from the active theme inside React consumers; module-level light-token snapshots do not update when appearance changes.
17. Use `constants/productLanguage.ts` for module labels; keep routes, capabilities, persisted keys and API identifiers unchanged.
18. Figma Make resource manifests are not rendered design evidence. Do not use dated local exports to claim fidelity to an updated file.
19. Android exports, Expo Go and a development APK are separate validation gates. Check the installed native client against the current React Native runtime.
20. Release the native splash after fonts and persisted appearance are ready; a successful auth response does not prove that the launch surface has stopped covering the application.
21. During device automation distinguish HomePlus controls from the draggable Expo Tools overlay. Its interception of a tap is not a product navigation failure.
22. Capture loaded content and use route-specific assertions; a module tile matching a heading can falsely satisfy a navigation check before the destination appears.
23. Evaluate module-grid breakpoints against width relative to font scale, not width alone; a passing navigation assertion does not prove that labels remain readable.
24. Keep clipping disabled for the small More module hub: Android compact/font-scaled QA demonstrated missing first-tile content with clipping enabled. Do not propagate this setting blindly to large virtualized lists.

25. Use AppPageHeader for peer page titles; subtitle is below the fixed title row so optional copy cannot shift its baseline. Keep real back callbacks and root-tab navigation intact.
26. Use Row for task-density horizontal items, preserving domain-owned amounts, role badges, stock controls and pending states. Keep module grids and file previews as explicit non-row surfaces.
27. InteractivePressable consumes the existing shared Reduced Motion subscription; do not create one native listener per list item. Flat rows use immediate opacity feedback without scaling their text/SVGs.
28. Before public Git publication, stage outside the live source tree, preserve remote history, scan the actual staged files, exclude private fixtures and runtime artifacts, and verify the remote SHA after a non-force push.
29. PlannerSheetHost is a separate modal authority from ActionSheet. For embedded form footer issues, inspect the actual host; Android transparent modals may retain full viewport behind the IME. Size against the real keyboard frame and keep domain scroll/submit ownership intact. Verify with an actual keyboard screenshot before claiming the fix.
