import Ionicons from '@expo/vector-icons/Ionicons';
import { Tabs } from 'expo-router';

import { colors } from '@/lib/theme';
import { useRobot } from '@/lib/robot';

export default function TabLayout() {
  const { status } = useRobot();
  return (
    <Tabs
      screenOptions={{
        tabBarActiveTintColor: colors.green,
        tabBarInactiveTintColor: colors.sub,
        tabBarStyle: { backgroundColor: colors.card, borderTopColor: colors.cardBorder },
        headerStyle: { backgroundColor: colors.bg },
        headerTitleStyle: { color: colors.text, fontWeight: '700' },
        headerTitleAlign: 'center',
        headerShadowVisible: false,
        sceneStyle: { backgroundColor: colors.bg },
      }}>
      <Tabs.Screen
        name="index"
        options={{
          title: 'Home',
          headerTitle: 'Robot Status',
          tabBarIcon: ({ color, size }) => <Ionicons name="home" size={size} color={color as string} />,
          tabBarBadge: status?.fire_detected ? '!' : undefined,
          tabBarBadgeStyle: { backgroundColor: colors.red },
        }}
      />
      <Tabs.Screen
        name="camera"
        options={{
          title: 'Camera',
          headerTitle: 'Live View',
          tabBarIcon: ({ color, size }) => <Ionicons name="camera-outline" size={size} color={color as string} />,
        }}
      />
      <Tabs.Screen
        name="history"
        options={{
          title: 'History',
          tabBarIcon: ({ color, size }) => <Ionicons name="time-outline" size={size} color={color as string} />,
        }}
      />
      <Tabs.Screen
        name="settings"
        options={{
          title: 'Setting',
          headerTitle: 'Settings',
          tabBarIcon: ({ color, size }) => <Ionicons name="settings-outline" size={size} color={color as string} />,
        }}
      />
    </Tabs>
  );
}
