module.exports = ({ config }) => {
  const googleMapsApiKey = process.env.GOOGLE_MAPS_API_KEY?.trim();

  return {
    ...config,

    plugins: [...(config.plugins || []), 'expo-asset', 'expo-status-bar', 'expo-video', 'expo-sharing', ['expo-audio', {
      microphonePermission: 'HomePlus necesita acceso al micrófono para grabar recuerdos de audio.',
    }]],

    extra: {
      ...config.extra,
      nativeCapabilities: {
        ...config.extra?.nativeCapabilities,
        googleMapsAndroid: Boolean(googleMapsApiKey),
      },
    },

    android: {
      ...config.android,
      config: {
        ...config.android?.config,
        ...(googleMapsApiKey ? {
          googleMaps: { apiKey: googleMapsApiKey },
        } : {}),
      },
    },
  };
};
