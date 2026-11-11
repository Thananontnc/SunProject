import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { colors } from '@/lib/theme';
import { fetchJson, normalizeUrl, RobotStatus, useRobot } from '@/lib/robot';

export default function SettingsScreen() {
  const { settings } = useRobot();
  // Re-mount the form when saved settings change (e.g. after loading from storage).
  return <SettingsForm key={`${settings.serverUrl}|${settings.lowWater}|${settings.lowBattery}`} />;
}

function SettingsForm() {
  const { settings, saveSettings, connected, status } = useRobot();
  const [server, setServer] = useState(settings.serverUrl);
  const [lowWater, setLowWater] = useState(String(settings.lowWater));
  const [lowBattery, setLowBattery] = useState(String(settings.lowBattery));
  const [test, setTest] = useState<string | null>(null);

  const clampPct = (v: string, fallback: number) => {
    const n = parseInt(v, 10);
    return Number.isFinite(n) ? Math.max(0, Math.min(100, n)) : fallback;
  };

  const save = async () => {
    await saveSettings({
      serverUrl: server,
      lowWater: clampPct(lowWater, settings.lowWater),
      lowBattery: clampPct(lowBattery, settings.lowBattery),
    });
    setTest('Saved');
  };

  const testConnection = async () => {
    setTest('Testing...');
    try {
      const s = await fetchJson<RobotStatus>(`${normalizeUrl(server)}/api/status`);
      setTest(`OK. Camera: ${s.camera ?? 'unknown'}, status: ${s.status}`);
    } catch (e) {
      setTest(`Failed: ${e instanceof Error ? e.message : String(e)}`);
    }
  };

  return (
    <ScrollView contentContainerStyle={styles.page} keyboardShouldPersistTaps="handled">
      <Text style={styles.section}>ROBOT CONNECTION</Text>
      <View style={styles.card}>
        <Text style={styles.label}>Raspberry Pi address</Text>
        <TextInput
          style={styles.input}
          value={server}
          onChangeText={setServer}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          placeholder="http://192.168.1.100:5000"
          placeholderTextColor={colors.muted}
        />
        <Text style={styles.hint}>
          Phone and Pi must be on the same WiFi. Find the Pi IP with: hostname -I
        </Text>
        <View style={styles.btnRow}>
          <Pressable style={[styles.btn, styles.btnGhost]} onPress={testConnection}>
            <Text style={styles.btnGhostText}>Test</Text>
          </Pressable>
          <Pressable style={styles.btn} onPress={save}>
            <Text style={styles.btnText}>Save</Text>
          </Pressable>
        </View>
        {!!test && <Text style={styles.hint}>{test}</Text>}
        <Text style={[styles.hint, { color: connected ? colors.green : colors.red }]}>
          {connected ? `Connected · camera: ${status?.camera ?? '-'}` : 'Not connected'}
        </Text>
      </View>

      <Text style={styles.section}>ALERTS</Text>
      <View style={styles.card}>
        <Row label="Low water warning (%)">
          <TextInput style={styles.small} value={lowWater} onChangeText={setLowWater} keyboardType="number-pad" onEndEditing={save} />
        </Row>
        <Row label="Low battery warning (%)">
          <TextInput style={styles.small} value={lowBattery} onChangeText={setLowBattery} keyboardType="number-pad" onEndEditing={save} />
        </Row>
        <Row label="Vibrate when fire detected">
          <Switch
            value={settings.vibrateOnFire}
            onValueChange={(v) => saveSettings({ vibrateOnFire: v })}
            trackColor={{ true: colors.green, false: colors.muted }}
          />
        </Row>
      </View>
    </ScrollView>
  );
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <View style={styles.row}>
      <Text style={styles.rowLabel}>{label}</Text>
      {children}
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: 16, paddingBottom: 40 },
  section: { color: colors.sub, fontSize: 12, fontWeight: '700', letterSpacing: 0.8, marginTop: 8, marginBottom: 8 },
  card: {
    backgroundColor: colors.card,
    borderRadius: 16,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: 16,
    marginBottom: 16,
    gap: 8,
  },
  label: { color: colors.text, fontWeight: '600' },
  input: {
    backgroundColor: colors.bg,
    color: colors.text,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    borderWidth: 1,
    borderColor: colors.cardBorder,
  },
  hint: { color: colors.sub, fontSize: 12 },
  btnRow: { flexDirection: 'row', gap: 10, marginTop: 4 },
  btn: { flex: 1, backgroundColor: colors.green, borderRadius: 10, paddingVertical: 11, alignItems: 'center' },
  btnText: { color: colors.bg, fontWeight: '700' },
  btnGhost: { backgroundColor: 'transparent', borderWidth: 1, borderColor: colors.green },
  btnGhostText: { color: colors.green, fontWeight: '700' },
  row: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingVertical: 4 },
  rowLabel: { color: colors.text, fontSize: 14, flex: 1 },
  small: {
    backgroundColor: colors.bg,
    color: colors.text,
    borderRadius: 8,
    width: 64,
    textAlign: 'center',
    paddingVertical: 6,
    borderWidth: 1,
    borderColor: colors.cardBorder,
  },
});
