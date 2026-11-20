const { getDefaultConfig } = require('expo/metro-config');

const config = getDefaultConfig(__dirname);
const defaultResolveRequest = config.resolver.resolveRequest;

/**
 * Expo Web compatibility shim.
 *
 * react-native-maps ships codegen-based native specs that react-native-web
 * cannot evaluate (codegenNativeComponent is not exported there). On web we
 * resolve the package to a lightweight surface that keeps the same public
 * component names so production screens render. Native builds are untouched:
 * the redirect applies only when platform === 'web'.
 */
config.resolver.resolveRequest = (context, moduleName, platform) => {
  if (platform === 'web' && (moduleName === 'react-native-maps' || moduleName.startsWith('react-native-maps/'))) {
    return {
      filePath: require.resolve('./web-shims/react-native-maps.web.tsx'),
      type: 'sourceFile',
    };
  }

  if (defaultResolveRequest) {
    return defaultResolveRequest(context, moduleName, platform);
  }
  return context.resolveRequest(context, moduleName, platform);
};

module.exports = config;
