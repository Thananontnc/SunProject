import Ionicons from '@expo/vector-icons/Ionicons';
import { useIsFocused } from 'expo-router';
import { useState } from 'react';
import { Modal, Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { WebView } from 'react-native-webview';

import { ConnectionBanner, Dot } from '@/components/ui';
import { colors } from '@/lib/theme';
import { useRobot } from '@/lib/robot';

/** MJPEG isn't supported by <Image>, so the stream is shown in a tiny WebView page. */
function Stream({ src }: { src: string }) {
  const html = `<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1">
  <style>html,body{margin:0;height:100%;background:#000;display:flex;align-items:center;justify-content:center;overflow:hidden}
  img{width:100%;height:100%;object-fit:contain}#e{color:#8B97AA;font:14px sans-serif;display:none}</style></head>
  <body><img src="${src}" onerror="this.style.display='none';document.getElementById('e').style.display='block'"><div id="e">No video. Is the server running?</div></body></html>`;
  return (
    <WebView
      originWhitelist={['*']}
      source={{ html }}
      style={{ backgroundColor: '#000' }}
      scrollEnabled={false}
      mixedContentMode="always"
      javaScriptEnabled
    />
  );
}

export default function CameraScreen() {
  const { status: s, connected, url } = useRobot();
  const focused = useIsFocused(); // stop streaming when tab is not visible (saves Pi CPU + phone battery)
  const [full, setFull] = useState(false);
  const [reloadKey, setReloadKey] = useState(0);
  const streamUrl = `${url('/stream')}?k=${reloadKey}`;

  const fire = !!s?.fire_detected;
  return (
    <ScrollView contentContainerStyle={styles.page}>
      <ConnectionBanner />
      <View style={styles.topRow}>
        <View style={styles.row}>
          <Dot color={connected ? colors.green : colors.red} size={8} />
          <Text style={styles.topText}>{connected ? 'Live' : 'Offline'}</Text>
        </View>
        <View style={styles.row}>
          <Ionicons name="wifi" size={14} color={colors.sub} />
          <Text style={styles.topText}>FPS: {s?.fps ?? '--'}</Text>
          <Pressable onPress={() => setReloadKey((k) => k + 1)} hitSlop={10}>
            <Ionicons name="refresh" size={18} color={colors.sub} />
          </Pressable>
          <Pressable onPress={() => setFull(true)} hitSlop={10}>
            <Ionicons name="expand" size={18} color={colors.text} />
          </Pressable>
        </View>
      </View>

      <View style={[styles.video, fire && { borderColor: colors.red }]}>
        {focused && !full && <Stream key={streamUrl} src={streamUrl} />}
      </View>

      <View style={styles.statsRow}>
        <Stat icon="car-outline" label="DISTANCE" value={s?.distance_m != null ? `${s.distance_m.toFixed(2)} m` : '--'} />
        <Stat icon="locate-outline" label="POSITION" value={s?.fire_position ?? '--'} accent={colors.green} />
      </View>
      <View style={styles.statsRow}>
        <Stat
          icon="flame"
          label="FIRE"
          value={fire ? `YES ${Math.round((s?.fire_confidence ?? 0) * 100)}%` : 'NO'}
          accent={fire ? colors.red : colors.sub}
        />
        <Stat icon="water" label="PUMP" value={s?.pump_on ? 'ON' : 'OFF'} accent={s?.pump_on ? colors.blue : colors.sub} />
      </View>
      <Text style={styles.note}>
        Detector: {s?.detector === 'yolo' ? `YOLO AI · ${s?.infer_ms ?? '-'} ms` : s?.detector === 'color' ? 'Color (no AI model)' : '--'}
        {'\n'}Monitor only. The robot drives itself.
      </Text>

      <Modal visible={full} animationType="fade" supportedOrientations={['portrait', 'landscape']} onRequestClose={() => setFull(false)}>
        <View style={{ flex: 1, backgroundColor: '#000' }}>
          {full && <Stream key={streamUrl + 'f'} src={streamUrl} />}
          <Pressable style={styles.close} onPress={() => setFull(false)} hitSlop={12}>
            <Ionicons name="close" size={26} color="#fff" />
          </Pressable>
        </View>
      </Modal>
    </ScrollView>
  );
}

function Stat({ icon, label, value, accent = colors.text }: { icon: any; label: string; value: string; accent?: string }) {
  return (
    <View style={styles.stat}>
      <Ionicons name={icon} size={22} color={colors.sub} />
      <View>
        <Text style={styles.statLabel}>{label}</Text>
        <Text style={[styles.statValue, { color: accent }]}>{value}</Text>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  page: { padding: 16, paddingBottom: 32 },
  topRow: { flexDirection: 'row', justifyContent: 'space-between', marginBottom: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  topText: { color: colors.text, fontSize: 13 },
  video: {
    aspectRatio: 4 / 3,
    backgroundColor: '#000',
    borderRadius: 14,
    overflow: 'hidden',
    borderWidth: 2,
    borderColor: colors.cardBorder,
  },
  statsRow: { flexDirection: 'row', gap: 12, marginTop: 12 },
  stat: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: colors.card,
    borderRadius: 14,
    borderWidth: 1,
    borderColor: colors.cardBorder,
    padding: 14,
  },
  statLabel: { color: colors.sub, fontSize: 11, fontWeight: '700', letterSpacing: 0.6 },
  statValue: { fontSize: 17, fontWeight: '700', marginTop: 2 },
  note: { color: colors.sub, fontSize: 12, textAlign: 'center', marginTop: 16 },
  close: { position: 'absolute', top: 48, right: 20, backgroundColor: '#0008', borderRadius: 20, padding: 6 },
});
