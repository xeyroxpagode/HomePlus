const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const read = (relativePath) => fs.readFileSync(path.join(root, relativePath), 'utf8');

test('bottom navigation keeps one crisp glyph and a route-driven moving indicator', () => {
  const navigationBar = read('front/mi-front-limpio/components/ui/FloatingNavigationBar.tsx');
  const navigator = read('front/mi-front-limpio/navigation/HomeTabNavigator.tsx');

  assert.match(navigationBar, /haptic="none"/);
  assert.match(navigationBar, /pressScale=\{1\}/);
  assert.match(navigationBar, /Animated\.multiply\(activePosition, itemWidth\)/);
  assert.match(navigationBar, /duration: motion\.navActive/);
  assert.doesNotMatch(navigationBar, /iconScale|activeIconLayer|inactiveIconLayer|Animated\.subtract/);
  assert.doesNotMatch(navigationBar, /renderToHardwareTextureAndroid|shouldRasterizeIOS/);

  const iconCalls = navigationBar.match(/<HomePlusIcon/g) ?? [];
  assert.equal(iconCalls.length, 2, 'one regular icon path plus one central-action icon path is expected');
  assert.match(navigator, /state\.routes\[state\.index\]/);
});

test('conversation preserves reading position and offers an explicit new-message jump', () => {
  const conversation = read('front/mi-front-limpio/screens/messages/MessagesConversationScreen.tsx');

  assert.match(conversation, /isNearBottom/);
  assert.match(conversation, /distanceFromBottom < 96/);
  assert.match(conversation, /setHasNewMessagesBelow\(true\)/);
  assert.match(conversation, /testID="messages\.newMessages"/);
  assert.doesNotMatch(conversation, /useEffect\(\(\) => \{ requestAnimationFrame\(\(\) => listRef\.current\?\.scrollToEnd/);
});

test('message to task keeps the conversation and exposes canonical Planner navigation', () => {
  const conversation = read('front/mi-front-limpio/screens/messages/MessagesConversationScreen.tsx');

  assert.match(conversation, /await createPlannerTask/);
  assert.match(conversation, /await linkMessageToTask/);
  assert.match(conversation, /testID="messages\.taskCreated\.open"/);
  assert.match(conversation, /navigation\.navigate\('TaskDetailFromMessage'/);
  assert.match(conversation, /returnTo: 'previous'/);
  assert.match(conversation, /messages\.action\.createTask\.error/);
});

test('shared loading buttons keep their layout dimensions stable', () => {
  const button = read('front/mi-front-limpio/components/ui/AppButton.tsx');

  assert.match(button, /<View style=\{\{ opacity: 0 \}\}>\{buttonContent\}<\/View>/);
  assert.match(button, /style=\{\{ position: 'absolute' \}\}/);
});
