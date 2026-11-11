import Ionicons from '@expo/vector-icons/Ionicons';
import { ComponentProps, ReactNode } from 'react';
import { StyleSheet, Text, View } from 'react-native';

import { colors } from '@/lib/theme';
import { useRobot } from '@/lib/robot';

type IconName = ComponentProps<typeof Ionicons>['name'];

export function InfoCard({
  icon,
  color,
  label,
  value,
  detail,
  right,
  children,
}: {
  icon: IconName;
  color: string;
  label: string;
  value: string;
  detail?: string;
  right?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <View style={styles.card}>
      <View style={styles.row}>
        <View style={[styles.iconRing, { borderColor: color + '66', backgroundColor: color + '1A' }]}>
          <Ionicons name={icon} size={26} color={color} />
        </View>
        <View style={{ flex: 1 }}>
          <Text style={[styles.label, { color: label === 'FIRE DETECTED' ? color : colors.sub }]}>{label}</Text>
          <Text style={[styles.value, { color }]}>{value}</Text>
          {!!detail && <Text style={styles.detail}>{detail}</Text>}
        </View>
        {right}
      </View>
      {children}
    </View>
  );
}

export function Bar({ pct, color }: { pct: number; color: string }) {
  return (
    <View style={styles.barTrack}>
      <View style={[styles.barFill, { width: `${Math.max(0, Math.min(100, pct))}%`, backgroundColor: color }]} />
    </View>
  );
}

export function Dot({ color, size = 10 }: { color: string; size?: number }) {
  return <View style={{ width: size, height: size, borderRadius: size / 2, backgroundColor: color }} />;
}

/** Red banner when the phone can't reach the Pi. */
export function ConnectionBanner() {
  const { connected, settings, lastError, status } = useRobot();
  if (connected && status?.robot_online !== false) return null;
  const text = !connected
    ? `Can't reach robot at ${settings.serverUrl}${lastError ? ` (${lastError})` : ''}. Check WiFi and Settings.`
    : 'Camera online, but the robot controller is not sending data.';
  return (
    <View style={[styles.banner, { backgroundColor: connected ? colors.orange + '22' : colors.red + '22' }]}>
      <Ionicons name="cloud-offline-outline" size={18} color={connected ? colors.orange : colors.red} />
      <Text style={[styles.bannerText, { color: connected ? colors.orange : colors.red }]}>{text}</Text>
    </View>
  );
}

export const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: 16,
    marginBottom: 12,
  },
  row: { flexDirection: 'row', alignItems: 'center', gap: 14 },
  iconRing: {
    width: 54,
    height: 54,
    borderRadius: 27,
    borderWidth: 2,
    alignItems: 'center',
    justifyContent: 'center',
  },
  label: { fontSize: 11, fontWeight: '700', letterSpacing: 0.8 },
  value: { fontSize: 22, fontWeight: '700', marginTop: 2 },
  detail: { fontSize: 12, color: colors.sub, marginTop: 3 },
  barTrack: { height: 8, borderRadius: 4, backgroundColor: colors.muted, marginTop: 14, overflow: 'hidden' },
  barFill: { height: '100%', borderRadius: 4 },
  banner: { flexDirection: 'row', gap: 8, alignItems: 'center', padding: 12, borderRadius: 12, marginBottom: 12 },
  bannerText: { flex: 1, fontSize: 13, fontWeight: '600' },
});
