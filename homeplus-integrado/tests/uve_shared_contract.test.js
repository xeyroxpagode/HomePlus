const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

function requireMinimumTouchTarget(size, minimum = 44) {
  if (size < minimum) throw new RangeError(`interactive target ${size} is below ${minimum}`);
  return size;
}

test('UVE fixture detects a compact control that regresses below 44', () => {
  assert.throws(() => requireMinimumTouchTarget(40), /below 44/);
  assert.equal(requireMinimumTouchTarget(44), 44);
});

test('theme exposes shared semantic geometry instead of screen-owned offsets', () => {
  const theme = read('front/mi-front-limpio/constants/theme.ts');
  assert.match(theme, /minimumInteractiveTarget: touchTargets\.normal/);
  assert.match(theme, /stableInputBorderWidth: 2/);
  assert.match(theme, /bottomBarHeight: componentSizes\.bottomNavHeight/);
  assert.match(theme, /bottomBarBreathingSpace: spacing\[2\]/);
});

test('selection primitives expose selected and disabled state to accessibility', () => {
  const chip = read('front/mi-front-limpio/components/ui/FilterChip.tsx');
  const segmented = read('front/mi-front-limpio/components/ui/SegmentedControl.tsx');
  assert.match(chip, /accessibilityState=\{\{ selected, disabled \}\}/);
  assert.match(segmented, /accessibilityState=\{\{ selected, checked:.*disabled: optionDisabled \}\}/s);
});

test('compact selection controls separate visual size from a 44 point touch target', () => {
  const chip = read('front/mi-front-limpio/components/ui/FilterChip.tsx');
  const segmented = read('front/mi-front-limpio/components/ui/SegmentedControl.tsx');
  assert.match(chip, /minHeight: visualErgonomics\.minimumInteractiveTarget/);
  assert.match(segmented, /minHeight: visualErgonomics\.minimumInteractiveTarget \+ inset \* 2/);
  assert.match(segmented, /minHeight: visualErgonomics\.minimumInteractiveTarget, paddingHorizontal/);
});

test('AppInput reserves focus border geometry and keeps error precedence', () => {
  const input = read('front/mi-front-limpio/components/ui/AppInput.tsx');
  assert.match(input, /borderWidth: visualErgonomics\.stableInputBorderWidth/);
  assert.doesNotMatch(input, /borderWidth: focused \? 2 : 1/);
  assert.match(input, /borderColor: hasError[\s\S]*\? colors\.danger\.base[\s\S]*: focused/);
});

test('UndoToast uses safe shell geometry, accessible Undo, and real reduced motion aware animation', () => {
  const toast = read('front/mi-front-limpio/components/ui/UndoToast.tsx');
  assert.match(toast, /useSafeAreaInsets/);
  assert.match(toast, /navigationGeometry\.bottomBarHeight/);
  assert.match(toast, /keyboardWillShow/);
  assert.match(toast, /AccessibilityInfo\.isReduceMotionEnabled/);
  assert.match(toast, /Animated\.timing/);
  assert.match(toast, /accessibilityLiveRegion="polite"/);
  assert.match(toast, /minHeight: touchTargets\.normal/);
  assert.match(toast, /if \(completedRef\.current\) return/);
  assert.doesNotMatch(toast, /bottom: 100/);
  assert.doesNotMatch(toast, /TouchableOpacity/);
});

test('AppScreen bottom clearance derives from shared navigation geometry', () => {
  const screen = read('front/mi-front-limpio/components/ui/AppScreen.tsx');
  assert.match(screen, /tab: navigationGeometry\.bottomBarHeight \+ navigationGeometry\.bottomBarBreathingSpace \+ spacing\[6\]/);
  assert.match(screen, /fab: navigationGeometry\.fabHeight \+ navigationGeometry\.bottomBarBreathingSpace \+ spacing\[12\]/);
  assert.doesNotMatch(screen, /tab: 96/);
  assert.doesNotMatch(screen, /fab: 112/);
});

test('Home contextual sections share one local header rhythm without changing their actions', () => {
  const home = read('front/mi-front-limpio/screens/home/HomePlannerSections.tsx');
  assert.match(home, /function HomeSectionHeader/);
  assert.equal((home.match(/<HomeSectionHeader/g) || []).length, 4);
  assert.match(home, /title="Necesita atención"/);
  assert.match(home, /title="Hoy"/);
  assert.match(home, /title="Próximamente"/);
  assert.match(home, /title="Qué cambió"/);
  assert.match(home, /accessibilityLabel=\{actionLabel\}/);
  assert.match(home, /actionLabel="Ver calendario"/);
  assert.match(home, /actionLabel="Ver actividad"/);
});

test('Messaging attachment actions are fully legible when enabled and visibly distinct when disabled', () => {
  const conversation = read('front/mi-front-limpio/screens/messages/MessagesConversationScreen.tsx');
  const actionOption = conversation.match(/actionOption: \{([^}]+)\}/)?.[1] ?? '';
  assert.doesNotMatch(actionOption, /opacity/);
  assert.match(conversation, /actionOptionPressed: \{ opacity: 0\.86/);
  assert.match(conversation, /actionDisabled: \{ opacity: 0\.45 \}/);
  assert.equal((conversation.match(/pressed && styles\.actionOptionPressed/g) || []).length, 5);
});

test('Presence map coordinates one status slot without changing map authority', () => {
  const presence = read('front/mi-front-limpio/screens/presence/PresenceScreen.tsx');
  assert.match(presence, /const statusOverlayBottom = embedded \? contextualContentBottom : standaloneContextualContentBottom/);
  assert.equal((presence.match(/styles\.statusOverlay/g) || []).length, 3);
  assert.match(presence, /!contextSection && !isPickingPlace && !error && !placeFeedback/);
  assert.match(presence, /error && members\.length > 0 && !placeFeedback/);
  assert.doesNotMatch(presence, /bottom: 144/);
  assert.match(presence, /onPanDrag=\{\(\) => \{ mapWasMovedByUser\.current = true; \}\}/);
  assert.match(presence, /onRegionChangeComplete=\{setManualRegion\}/);
});

test('safe temporary overlays dismiss from backdrop without propagating inside taps', () => {
  const conversation = read('front/mi-front-limpio/screens/messages/MessagesConversationScreen.tsx');
  const inbox = read('front/mi-front-limpio/screens/messages/MessagesInboxScreen.tsx');
  const actionSheet = read('front/mi-front-limpio/components/ui/ActionSheet.tsx');
  assert.match(conversation, /testID="messages\.taskPicker"[\s\S]*onPress=\{\(\) => setTaskPickerOpen\(false\)\}/);
  assert.match(conversation, /onPress=\{\(event\) => event\.stopPropagation\(\)\} accessibilityRole="none"/);
  assert.match(inbox, /style=\{styles\.modalScrim\} onPress=\{\(\) => setChooserOpen\(false\)\}/);
  assert.match(inbox, /style=\{styles\.sheet\} onPress=\{\(event\) => event\.stopPropagation\(\)\}/);
  assert.match(actionSheet, /keyboardAware && keyboardVisible/);
  assert.match(actionSheet, /disabled=\{closeDisabled\}/);
});

test('keyboard-aware near-full sheets resize their content instead of translating the whole card', () => {
  const actionSheet = read('front/mi-front-limpio/components/ui/ActionSheet.tsx');
  assert.match(actionSheet, /keyboardAware[\s\S]*height: '90%' as const[\s\S]*maxHeight: safeSheetHeight/);
  assert.match(actionSheet, /behavior=\{Platform\.OS === 'ios' \? 'height' : undefined\}/);
  assert.match(actionSheet, /keyboardAvoiding: \{ flex: 1, width: '100%', justifyContent: 'flex-end' \}/);
  assert.doesNotMatch(actionSheet, /keyboardAvoiding: \{ flexShrink: 1/);
});

test('More remains a stable responsive module hub with the original destinations', () => {
  const more = read('front/mi-front-limpio/screens/MoreScreen.tsx');
  for (const route of ['HomeCloud', 'FeedFamiliar', 'Finance', 'Inventory']) {
    assert.match(more, new RegExp(`screen: '${route}'`));
  }
  assert.match(more, /function ModuleTile/);
  assert.match(more, />\s*HOMEPLUS\s*</);
  assert.match(more, /flexWrap: 'wrap'/);
  assert.match(more, /flexBasis: '48%'/);
  assert.match(more, /maxWidth: '48%'/);
  assert.match(more, /flexGrow: 0/);
  assert.match(more, /flexDirection: 'row'/);
  assert.match(more, /width \/ fontScale < 360 \|\| fontScale >= 1\.6/);
  assert.match(more, /removeClippedSubviews: false/);
  assert.doesNotMatch(more, /numberOfLines=\{2\} style=\{styles\.moduleLabel\}/);
  assert.match(more, /haptic="none"/);
  assert.match(more, /pressScale=\{1\}/);
  assert.match(more, /__DEV__ && session/);
  assert.doesNotMatch(more, /\.sort\(/);
  assert.doesNotMatch(more, /Frecuentes|TextInput|useQuery|subscribe/);
});

test('navbar continues to use canonical 44 point interactive targets', () => {
  const navigation = read('front/mi-front-limpio/components/ui/FloatingNavigationBar.tsx');
  assert.match(navigation, /minHeight: touchTargets\.normal/);
  assert.match(navigation, /width: touchTargets\.normal/);
  assert.match(navigation, /height: touchTargets\.normal/);
});

test('Home uses its top bar inset and Planner screens own their exposed top safe area', () => {
  const home = read('front/mi-front-limpio/screens/home/HomeCoordinador.tsx');
  const planner = read('front/mi-front-limpio/screens/planner/PlannerScreen.tsx');
  const taskDetail = read('front/mi-front-limpio/screens/planner/TaskDetailScreen.tsx');
  assert.match(home, /safeAreaEdges=\{\['left', 'right', 'bottom'\]\}/);
  const shell = read('front/mi-front-limpio/navigation/StandardShell.tsx');
  assert.match(shell, /return <HomeTabNavigator \/>/);
  assert.match(planner, /edges=\{\['top', 'left', 'right'\]\}/);
  assert.match(taskDetail, /testID="screen\.planner\.taskDetail"[\s\S]*edges=\{\['top', 'left', 'right'\]\}/);
});

test('task detail action and inline calendar respect floating navigation and iOS safe areas', () => {
  const taskDetail = read('front/mi-front-limpio/screens/planner/TaskDetailScreen.tsx');
  const actionSheet = read('front/mi-front-limpio/components/ui/ActionSheet.tsx');
  assert.match(taskDetail, /bottom: navigationGeometry\.bottomBarHeight[\s\S]*navigationGeometry\.bottomBarBreathingSpace[\s\S]*insets\.bottom/);
  assert.match(actionSheet, /dayNamesShort: \['Do', 'Lu', 'Ma', 'Mi', 'Ju', 'Vi', 'Sá'\]/);
  assert.match(actionSheet, /const topClearance = Math\.max\(insets\.top \+ theme\.spacing\[6\]/);
  assert.match(actionSheet, /maxHeight: height - topClearance/);
  assert.match(actionSheet, /paddingBottom: Math\.max\(insets\.bottom, theme\.spacing\[3\]\)/);
  assert.match(actionSheet, /styles\.dateContext/);
});

test('places use real geocoding and reject misleading street-scale fixes', () => {
  const presence = read('front/mi-front-limpio/screens/presence/PresenceScreen.tsx');
  const sharing = read('front/mi-front-limpio/services/presenceLocationSharing.ts');
  const places = read('front/mi-front-limpio/components/family/PlacesBottomSheet.tsx');
  assert.match(presence, /Location\.geocodeAsync\(query\)/);
  assert.match(presence, /Location\.reverseGeocodeAsync/);
  assert.match(presence, /MAXIMUM_PLACE_FIX_ACCURACY_METERS = 50/);
  assert.match(sharing, /MAXIMUM_ACCEPTABLE_ACCURACY_METERS = 100/);
  assert.match(sharing, /accuracy: Location\.Accuracy\.High/);
  assert.doesNotMatch(places, /SEARCH_RESULTS|DEMO_NEARBY_PLACES|Av\. Corrientes/);
  assert.match(places, /onSearchAddress/);
});

test('Planner primary claim callback is initialized before action resolution', () => {
  const detail = read('front/mi-front-limpio/screens/planner/TaskDetailScreen.tsx');
  assert.ok(detail.indexOf('const handleClaim = async') < detail.indexOf('const primaryAction = getPrimaryAction()'));
  assert.match(detail, /actionKey: 'claim'/);
  assert.match(detail, /loading=\{savingAction === primaryAction\.actionKey\}/);
});

test('primary destinations share compact page heading and Planner exposes add without losing management actions', () => {
  const planner = read('front/mi-front-limpio/screens/planner/PlannerScreen.tsx');
  const inventory = read('front/mi-front-limpio/screens/inventory/InventarioScreen.tsx');
  const more = read('front/mi-front-limpio/screens/MoreScreen.tsx');
  assert.match(planner, /<AppPageHeader/);
  assert.match(inventory, /<AppPageHeader/);
  assert.match(more, /<AppPageHeader/);
  assert.match(planner, /accessibilityLabel="Agregar en Organizador"/);
  assert.match(planner, /Biblioteca de presets/);
  assert.match(planner, /Papelera/);
});
