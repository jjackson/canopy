import { Video, Img, staticFile, useVideoConfig } from "remotion";
import { theme } from "../theme";

interface Props {
  asset: string;
  // Per-beat caption was a third text channel competing with the
  // narration caption bar. Kept as an optional escape hatch but
  // suppressed by default so we don't double-up text on screen.
  caption?: string;
  showCaption?: boolean;
  // Where in the source clip to begin playback (when asset is a video).
  // Mirrors clip-level start_seconds for scene clips so per-clip range
  // editing works the same way for product beats.
  startSeconds?: number;
}

const isVideo = (s: string) => /\.(mp4|webm|mov)$/i.test(s);

// Detect web-dashboard / browser screencasts from the asset path so we
// can drop them out of the 9:16 phone bezel that mobile FLW-app
// screencasts use. Convention is documented in spec.yaml's manifest
// comment: `mobile-*` = phone screencasts, `web-*` = web/Labs
// dashboards, `field-*` = b-roll. After applyManifestRefs() the alias
// stem is still visible as the filename basename — e.g.
// `assets/programs/chc/web-microplan.mp4` — so a basename match is
// the safe signal.
const isWebScreencast = (s: string) => {
  const base = s.split("/").pop() ?? s;
  return /^web[-_]/i.test(base);
};

export const AppScreen: React.FC<Props> = ({ asset, caption, showCaption = false, startSeconds = 0 }) => {
  const { fps, width: canvasW, height: canvasH } = useVideoConfig();
  const src = asset.startsWith("http") ? asset : staticFile(asset);
  const startFrom = Math.round(startSeconds * fps);

  // Web screencasts fill the whole canvas and are shown WHOLE (objectFit
  // contain) — the capture's own aspect ratio is respected, never cropped.
  // Dashboards are often taller than 16:9 (e.g. 1280×1000) because a short
  // 16:9 viewport makes dense tables/maps too small/cut-off to read; contain
  // shows every captured row at the largest size that fits, with the canvas
  // background filling any side/letterbox margin (a 16:9 capture fills edge to
  // edge, a taller capture sits centered with light margins). Mobile clips keep
  // the 540×960 phone bezel + cover.
  const web = isWebScreencast(asset);
  const fit: "contain" | "cover" = web ? "contain" : "cover";
  const frameStyle: React.CSSProperties = web
    ? {
        width: canvasW,
        height: canvasH,
        background: theme.colors.background,
      }
    : {
        width: 540,
        height: 960,
        borderRadius: 56,
        background: "#000",
        padding: 16,
        boxShadow: "0 24px 64px rgba(0,0,0,0.25)",
      };
  const innerRadius = web ? 0 : 40;

  return (
    <div
      style={{
        position: "absolute",
        inset: 0,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        background: theme.colors.background,
        fontFamily: theme.fonts.sans,
      }}
    >
      <div style={frameStyle}>
        <div style={{ width: "100%", height: "100%", borderRadius: innerRadius, overflow: "hidden" }}>
          {isVideo(asset) ? (
            <Video
              src={src}
              startFrom={startFrom}
              style={{ width: "100%", height: "100%", objectFit: fit }}
              onError={() => {
                /* Missing asset — render blank frame; drop real file into assets/ to fix */
              }}
            />
          ) : (
            <Img src={src} style={{ width: "100%", height: "100%", objectFit: fit }} />
          )}
        </div>
      </div>
      {caption && showCaption && (
        <div
          style={{
            position: "absolute",
            right: 96,
            top: "50%",
            transform: "translateY(-50%)",
            maxWidth: 560,
            color: theme.colors.foreground,
            fontSize: 42,
            fontWeight: 600,
          }}
        >
          {caption}
        </div>
      )}
    </div>
  );
};
