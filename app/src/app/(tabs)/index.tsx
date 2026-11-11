import Ionicons from '@expo/vector-icons/Ionicons';
import { ScrollView, StyleSheet, Text, View } from 'react-native';

import { Bar, ConnectionBanner, Dot, InfoCard } from '@/components/ui';
import { colors, levelColor, statusColor } from '@/lib/theme';
import { useRobot } from '@/lib/robot';

const pct = (v: number | null | undefined) => (v == null ? '--' : `${Math.round(v)}%`);

export default function HomeScreen() {
  const { status: s, settings } = useRobot();

  const fire = !!s?.fire_detected;
  const water = s?.water_level ?? null;
  const battery = s?.battery ?? null;
  const waterLow = water != null && water <= settings.lowWater;
  const batteryLow = battery != null && battery <= settings.lowBattery;

  return (
    <ScrollView contentContainerStyle={styles.page}>
      <ConnectionBanner />

      <InfoCard
        icon="hardware-chip-outline"
        color={statusColor(s?.status ?? '')}
        label="STATUS"
        value={s?.status ?? '--'}
        detail={s?.status_detail}
      />

      <InfoCard
        icon="flame"
        color={fire ? colors.red : colors.sub}
        label="FIRE DETECTED"
        value={fire ? 'YES' : 'NO'}
        detail={
          fire
            ? `Fire is detected · ${Math.round((s?.fire_confidence ?? 0) * 100)}% · ${s?.fire_position ?? ''}`
            : 'No fire in view'
        }
        right={fire ? <Dot color={colors.red} /> : undefined}
      />

      <InfoCard
        icon="water"
        color={s?.pump_on ? colors.blue : colors.sub}
        label="PUMP"
        value={s?.pump_on ? 'ON' : 'OFF'}
        detail={s?.pump_on ? 'Water pump is spraying' : 'Water pump is off'}
        right={<Dot color={s?.pump_on ? colors.blue : colors.muted} size={14} />}
      />

      <InfoCard
        icon={batteryLow ? 'battery-dead' : battery != null && battery > 60 ? 'battery-full' : 'battery-half'}
        color={battery == null ? colors.sub : levelColor(battery, settings.lowBattery)}
        label="BATTERY"
        value={pct(battery)}
        detail={batteryLow ? 'Battery low. Charge the robot.' : undefined}>
        {battery != null && <Bar pct={battery} color={levelColor(battery, settings.lowBattery)} />}
      </InfoCard>

      <InfoCard
        icon="beaker-outline"
        color={water == null ? colors.sub : levelColor(water, settings.lowWater)}
        label="WATER LEVEL"
        value={pct(water)}>
        {water != null && <Bar pct={water} color={levelColor(water, settings.lowWater)} />}
        {waterLow && (
          <View style={styles.warn}>
            <Ionicons name="warning" size={16} color={colors.red} />
            <Text style={styles.warnText}>Water level too low. Refill water.</Text>
          </View>
        )}
      </InfoCard>

      {s?.simulated && <Text style={styles.sim}>Simulation mode: values are fake (server SIMULATE=1)</Text>}
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  page: { padding: 16, paddingBottom: 32 },
  warn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 12 },
  warnText: { color: colors.red, fontWeight: '700', fontSize: 13 },
  sim: { color: colors.sub, fontSize: 12, textAlign: 'center', marginTop: 4 },
});
