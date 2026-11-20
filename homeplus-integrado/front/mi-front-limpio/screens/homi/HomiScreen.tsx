import React from 'react';
import { SafeAreaView, StyleSheet } from 'react-native';
import { HomiSurface } from '../../components/homi/HomiSurface';

export function HomiScreen() {
  return (
    <SafeAreaView style={styles.container}>
      <HomiSurface />
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1 },
});
