import { Stack } from 'expo-router';
import { StatusBar } from 'expo-status-bar';

import { RobotProvider } from '@/lib/robot';

export default function RootLayout() {
  return (
    <RobotProvider>
      <StatusBar style="light" />
      <Stack screenOptions={{ headerShown: false }}>
        <Stack.Screen name="(tabs)" />
      </Stack>
    </RobotProvider>
  );
}
