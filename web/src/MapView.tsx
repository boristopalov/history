import maplibregl from "maplibre-gl";
import { useEffect, useMemo, useRef, useState } from "react";
import { eventText, isActivity, MAX_GAP_S, positionAt, type Track } from "./track";
import type { HistoryEvent } from "./types";

const STYLE = "https://tiles.openfreemap.org/styles/positron";
const PATH = "#6366f1";
const PIN = "#f59e0b";
const IN_RANGE = "#0ea5e9";
const MAX_POPUP_EVENTS = 5;
const FOLLOW_MARGIN_PX = 140;

export type Point = { lat: number; lon: number };

/** A pinned query result. */
export type Pin = Point & { ts: number | null };

/** One move of the camera. A new object is a new move, even to the same place. */
export type Camera = { points: Point[] };

/** The edges of the map hidden behind floating panels, in pixels. */
export type Padding = { top: number; bottom: number; left: number; right: number };

type Props = {
  track: Track;
  events: HistoryEvent[];
  pins: Pin[];
  t: number;
  rangeS: number;
  playing: boolean;
  camera: Camera | null;
  padding: Padding;
  onSeek: (t: number) => void;
  onPickPin: (pin: Pin) => void;
};

function collection(features: GeoJSON.Feature[]): GeoJSON.FeatureCollection {
  return { type: "FeatureCollection", features };
}

function point(lat: number, lon: number, properties: GeoJSON.GeoJsonProperties): GeoJSON.Feature {
  return { type: "Feature", geometry: { type: "Point", coordinates: [lon, lat] }, properties };
}

function isWebLink(url: string): boolean {
  try {
    return ["http:", "https:"].includes(new URL(url).protocol);
  } catch {
    return false;
  }
}

/** Event text comes from other people, so it only ever goes in as text. */
function popupContent(events: HistoryEvent[], onSeek: (t: number) => void): HTMLElement {
  const root = document.createElement("div");
  root.className = "popup";
  for (const event of events.slice(0, MAX_POPUP_EVENTS)) {
    const row = document.createElement("button");
    row.className = "popup-event";
    row.onclick = () => onSeek(event.ts);

    const heading = document.createElement("div");
    heading.className = "popup-meta";
    const time = new Date(event.ts * 1000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
    heading.textContent = `${event.source} · ${time}`;

    const text = document.createElement("div");
    text.className = "popup-text";
    text.textContent = eventText(event);
    row.append(heading, text);
    root.append(row);

    const gap = event.location?.gap_s ?? 0;
    if (gap >= 60) {
      const note = document.createElement("div");
      note.className = "popup-note";
      note.textContent = `Placed by a fix ${Math.round(gap / 60)} min away`;
      root.append(note);
    }
    if (event.url && isWebLink(event.url)) {
      const link = document.createElement("a");
      link.className = "popup-link";
      link.href = event.url;
      link.target = "_blank";
      link.rel = "noreferrer noopener";
      link.textContent = new URL(event.url).hostname;
      root.append(link);
    }
  }
  if (events.length > MAX_POPUP_EVENTS) {
    const more = document.createElement("div");
    more.className = "popup-note";
    more.textContent = `and ${events.length - MAX_POPUP_EVENTS} more here`;
    root.append(more);
  }
  return root;
}

export function MapView({
  track,
  events,
  pins,
  t,
  rangeS,
  playing,
  camera,
  padding,
  onSeek,
  onPickPin,
}: Props) {
  const container = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const marker = useRef<maplibregl.Marker | null>(null);
  const [ready, setReady] = useState(false);

  // The map's click handlers live as long as the map, so they read these through refs.
  const eventsRef = useRef(events);
  const seekRef = useRef(onSeek);
  const pinsRef = useRef(pins);
  const pickPinRef = useRef(onPickPin);
  useEffect(() => {
    eventsRef.current = events;
    seekRef.current = onSeek;
    pinsRef.current = pins;
    pickPinRef.current = onPickPin;
  });

  useEffect(() => {
    const instance = new maplibregl.Map({
      container: container.current as HTMLDivElement,
      style: STYLE,
      center: [0, 25],
      zoom: 1.4,
      attributionControl: false,
    });
    instance.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-left");
    instance.addControl(new maplibregl.AttributionControl({ compact: true }), "top-left");
    map.current = instance;

    const element = document.createElement("div");
    element.className = "me";
    marker.current = new maplibregl.Marker({ element });

    instance.on("load", () => {
      const empty = collection([]);
      for (const id of ["segments", "fixes", "events", "pins"]) {
        instance.addSource(id, { type: "geojson", data: empty });
      }
      instance.addLayer({
        id: "gaps",
        type: "line",
        source: "segments",
        filter: ["==", ["get", "gap"], true],
        layout: { "line-cap": "round" },
        paint: { "line-color": PATH, "line-opacity": 0.3, "line-width": 1.5, "line-dasharray": [1, 3] },
      });
      instance.addLayer({
        id: "path-ahead",
        type: "line",
        source: "segments",
        filter: ["==", ["get", "gap"], false],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": PATH, "line-opacity": 0.22, "line-width": 2.5 },
      });
      instance.addLayer({
        id: "path-behind",
        type: "line",
        source: "segments",
        filter: ["==", ["get", "gap"], false],
        layout: { "line-cap": "round", "line-join": "round" },
        paint: { "line-color": PATH, "line-width": 2.5 },
      });
      instance.addLayer({
        id: "fixes",
        type: "circle",
        source: "fixes",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2, 15, 4],
          "circle-color": PATH,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1,
        },
      });
      instance.addLayer({
        id: "events",
        type: "circle",
        source: "events",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 2, 15, 4],
          "circle-color": "#475069",
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1,
        },
      });
      instance.addLayer({
        id: "events-in-range",
        type: "circle",
        source: "events",
        paint: {
          "circle-radius": ["interpolate", ["linear"], ["zoom"], 10, 3.5, 15, 6],
          "circle-color": IN_RANGE,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 1.5,
        },
      });
      // Invisible, and larger than the dots, so that they're easy to click or tap.
      instance.addLayer({
        id: "events-target",
        type: "circle",
        source: "events",
        paint: { "circle-radius": 12, "circle-opacity": 0 },
      });
      instance.addLayer({
        id: "pins",
        type: "circle",
        source: "pins",
        paint: {
          "circle-radius": 6,
          "circle-color": PIN,
          "circle-stroke-color": "#ffffff",
          "circle-stroke-width": 2,
        },
      });

      instance.on("click", "events-target", (click) => {
        const hits = instance.queryRenderedFeatures(click.point, { layers: ["events-target"] });
        const here = hits
          .map((hit) => eventsRef.current[hit.properties.index as number])
          .filter((event) => event !== undefined)
          .sort((a, b) => a.ts - b.ts);
        if (here.length === 0) return;
        new maplibregl.Popup({ maxWidth: "300px", offset: 10 })
          .setLngLat(click.lngLat)
          .setDOMContent(popupContent(here, (ts) => seekRef.current(ts)))
          .addTo(instance);
      });
      instance.on("click", "pins", (click) => {
        const pin = pinsRef.current[click.features?.[0]?.properties.index as number];
        if (pin) pickPinRef.current(pin);
      });
      for (const layer of ["events-target", "pins"]) {
        instance.on("mouseenter", layer, () => (instance.getCanvas().style.cursor = "pointer"));
        instance.on("mouseleave", layer, () => (instance.getCanvas().style.cursor = ""));
      }
      // Compact attribution starts expanded. Fold it to its button, clear of the map.
      const attribution = instance.getContainer().querySelector(".maplibregl-ctrl-attrib");
      attribution?.classList.remove("maplibregl-compact-show");
      attribution?.removeAttribute("open");
      setReady(true);
    });

    return () => {
      instance.remove();
      map.current = null;
      setReady(false);
    };
  }, []);

  const segments = useMemo(() => {
    const lines: GeoJSON.Feature[] = [];
    track.fixes.forEach((fix, i) => {
      const next = track.fixes[i + 1];
      if (!next) return;
      lines.push({
        type: "Feature",
        geometry: {
          type: "LineString",
          coordinates: [
            [fix.lon, fix.lat],
            [next.lon, next.lat],
          ],
        },
        properties: { t: next.t, gap: next.t - fix.t > MAX_GAP_S },
      });
    });
    return collection(lines);
  }, [track]);

  useEffect(() => {
    if (!ready || !map.current) return;
    const source = (id: string) => map.current?.getSource(id) as maplibregl.GeoJSONSource;
    source("segments").setData(segments);
    source("fixes").setData(
      collection(track.fixes.map((fix) => point(fix.lat, fix.lon, { t: fix.t }))),
    );
    source("events").setData(
      collection(
        events.flatMap((event, index) =>
          isActivity(event) && event.location
            ? [
                point(event.location.lat, event.location.lon, {
                  t: event.ts,
                  end: event.end_ts ?? event.ts,
                  index,
                }),
              ]
            : [],
        ),
      ),
    );
  }, [ready, segments, track, events]);

  useEffect(() => {
    if (!ready) return;
    const source = map.current?.getSource("pins") as maplibregl.GeoJSONSource;
    source.setData(collection(pins.map((pin, index) => point(pin.lat, pin.lon, { index }))));
  }, [ready, pins]);

  // The day unfolds up to the playhead.
  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance) return;
    instance.setFilter("path-behind", [
      "all",
      ["==", ["get", "gap"], false],
      ["<=", ["get", "t"], t],
    ]);
    instance.setFilter("fixes", ["<=", ["get", "t"], t]);
    instance.setFilter("events", ["<=", ["get", "t"], t]);
    const inRange: maplibregl.ExpressionSpecification = [
      "all",
      ["<=", ["get", "t"], t + rangeS],
      [">=", ["get", "end"], t - rangeS],
    ];
    instance.setFilter("events-in-range", inRange);
    // Anything lit up has to be clickable, including events just ahead of the playhead.
    instance.setFilter("events-target", ["any", ["<=", ["get", "t"], t], inRange]);

    const position = positionAt(track, t);
    if (!position || !marker.current) {
      marker.current?.remove();
      return;
    }
    marker.current.setLngLat([position.lon, position.lat]).addTo(instance);
    marker.current.getElement().classList.toggle("stale", position.stale);

    if (playing && !instance.isEasing()) {
      const { x, y } = instance.project([position.lon, position.lat]);
      const { clientWidth: width, clientHeight: height } = instance.getContainer();
      const inView =
        x > padding.left + FOLLOW_MARGIN_PX / 2 &&
        x < width - padding.right - FOLLOW_MARGIN_PX / 2 &&
        y > padding.top + FOLLOW_MARGIN_PX / 2 &&
        y < height - padding.bottom - FOLLOW_MARGIN_PX / 2;
      if (!inView) {
        instance.easeTo({ center: [position.lon, position.lat], padding, duration: 700 });
      }
    }
  }, [ready, track, t, rangeS, playing, padding]);

  useEffect(() => {
    const instance = map.current;
    if (!ready || !instance || !camera || camera.points.length === 0) return;
    if (camera.points.length === 1) {
      const [{ lat, lon }] = camera.points;
      instance.flyTo({
        center: [lon, lat],
        zoom: Math.max(instance.getZoom(), 14),
        padding,
        duration: 900,
      });
      return;
    }
    const bounds = new maplibregl.LngLatBounds();
    for (const { lat, lon } of camera.points) bounds.extend([lon, lat]);
    instance.fitBounds(bounds, { padding, maxZoom: 15.5, duration: 800 });
    // `padding` is left out on purpose: opening the panel shouldn't move the camera.
  }, [ready, camera]);

  return <div ref={container} className="map" />;
}
