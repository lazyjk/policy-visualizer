/**
 * Custom React Flow node types.
 * Default colors match the existing Graphviz renderer in src/renderer.py.
 * Node fill colors are user-configurable via the StylePanel (per shape).
 */
import React, { useState, useRef, useEffect } from "react";
import { Handle, Position, type NodeProps, NodeToolbar, useReactFlow, NodeResizer } from "@xyflow/react";
import { useEditor, EditorContent } from "@tiptap/react";
import { Extension } from "@tiptap/core";
import StarterKit from "@tiptap/starter-kit";
import TiptapImage from "@tiptap/extension-image";
import { TextStyle } from "@tiptap/extension-text-style";
import { FontFamily } from "@tiptap/extension-font-family";

export interface NodeColors {
  start: string;
  decision: string;
  process: string;
  action: string;
  end: string;
  annotation: string;
}

export const DEFAULT_NODE_COLORS: NodeColors = {
  start:      "#AED6F1",
  decision:   "#FAD7A0",
  process:    "#A9DFBF",
  action:     "#D7BDE2",
  end:        "#F1948A",
  annotation: "#FFFDE7",
};

interface NodeData {
  label: string;
  sub_label?: string;
  colors?: NodeColors;
  [key: string]: unknown;
}

function multilineLabel(label: string) {
  return label.split("\n").map((line, i) => (
    <React.Fragment key={i}>
      {i > 0 && <br />}
      {line}
    </React.Fragment>
  ));
}

// Number of label lines shown inside the diamond before truncating.
// Single-predicate conditions (3–4 lines) fit; multi-predicate ones get a tooltip.
const DIAMOND_LABEL_THRESHOLD = 4;

function truncateLines(label: string, maxLines: number): { display: string; overflow: number } {
  const lines = label.split("\n");
  if (lines.length <= maxLines) return { display: label, overflow: 0 };
  return { display: lines.slice(0, maxLines).join("\n"), overflow: lines.length - maxLines };
}

const tooltipStyle: React.CSSProperties = {
  background: "white",
  border: "1px solid #ccc",
  borderRadius: 6,
  padding: "8px 12px",
  fontSize: 11,
  fontFamily: "Helvetica, Arial, sans-serif",
  lineHeight: 1.4,
  boxShadow: "0 2px 8px rgba(0,0,0,0.15)",
  maxWidth: 280,
  wordBreak: "break-word",
  pointerEvents: "none",
};

const baseStyle: React.CSSProperties = {
  fontSize: 11,
  fontFamily: "Helvetica, Arial, sans-serif",
  textAlign: "center",
  padding: "6px 10px",
  display: "flex",
  alignItems: "center",
  justifyContent: "center",
  lineHeight: 1.4,
  minWidth: 90,
  maxWidth: 200,
  wordBreak: "break-word",
  overflow: "hidden",
};

// start — ellipse
export function StartNode({ data }: NodeProps) {
  const d = data as NodeData;
  const fill = d.colors?.start ?? DEFAULT_NODE_COLORS.start;
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: fill,
        borderRadius: "50%",
        border: "2px solid #5DADE2",
        padding: "10px 14px",
      }}
    >
      <Handle type="source" position={Position.Right} />
      <div>{multilineLabel(d.label)}</div>
    </div>
  );
}

// decision — diamond (rotated square)
// Outer container is fixed at 220×220 to match NODE_SIZE_FALLBACKS in FlowDiagram.tsx.
// Inner square is 150×150; rotated 45° its bounding box is ~212px, which fits inside.
// overflow:hidden on the inner div clips text to the diamond shape.
// When the label exceeds DIAMOND_LABEL_THRESHOLD lines, the overflow is truncated and
// a styled NodeToolbar tooltip reveals the full condition on hover.
export function DecisionNode({ data }: NodeProps) {
  const d = data as NodeData;
  const [hovered, setHovered] = useState(false);
  const { display, overflow } = truncateLines(d.label, DIAMOND_LABEL_THRESHOLD);
  const isTruncated = overflow > 0;
  const fill = d.colors?.decision ?? DEFAULT_NODE_COLORS.decision;

  return (
    <div
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
      style={{
        position: "relative",
        width: 220,
        height: 220,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
      }}
    >
      {isTruncated && (
        <NodeToolbar isVisible={hovered} position={Position.Right}>
          <div style={tooltipStyle}>{multilineLabel(d.label)}</div>
        </NodeToolbar>
      )}
      <Handle type="target" position={Position.Left} id="left" />
      <Handle type="target" position={Position.Top} id="top" />
      <div
        style={{
          background: fill,
          border: "2px solid #E59866",
          transform: "rotate(45deg)",
          width: 150,
          height: 150,
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          flexShrink: 0,
          overflow: "hidden",
        }}
      >
        <div
          style={{
            transform: "rotate(-45deg)",
            textAlign: "center",
            fontSize: 10,
            fontFamily: "Helvetica, Arial, sans-serif",
            lineHeight: 1.3,
            maxWidth: 130,
            wordBreak: "break-word",
            padding: "4px",
          }}
        >
          {multilineLabel(display)}
          {isTruncated && (
            <div style={{ fontSize: 9, opacity: 0.65, marginTop: 2 }}>+{overflow} more…</div>
          )}
        </div>
      </div>
      <Handle type="source" position={Position.Right} id="yes" />
      <Handle type="source" position={Position.Bottom} id="no" />
    </div>
  );
}

// process — plain rectangle
export function ProcessNode({ data }: NodeProps) {
  const d = data as NodeData;
  const fill = d.colors?.process ?? DEFAULT_NODE_COLORS.process;
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: fill,
        border: "2px solid #52BE80",
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div>{multilineLabel(d.label)}</div>
      <Handle type="source" position={Position.Right} />
      <Handle type="source" position={Position.Bottom} id="fail" />
      <Handle type="source" position={Position.Left} id="continue" style={{ top: "75%" }} />
    </div>
  );
}

// action — rounded rectangle
export function ActionNode({ data }: NodeProps) {
  const d = data as NodeData;
  const fill = d.colors?.action ?? DEFAULT_NODE_COLORS.action;
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: fill,
        border: "2px solid #A569BD",
        borderRadius: 12,
      }}
    >
      <Handle type="target" position={Position.Left} />
      <div>{multilineLabel(d.label)}</div>
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

// end — double circle
export function EndNode({ data }: NodeProps) {
  const d = data as NodeData;
  const fill = d.colors?.end ?? DEFAULT_NODE_COLORS.end;
  return (
    <div
      title={[d.label, d.sub_label].filter(Boolean).join("\n")}
      style={{
        ...baseStyle,
        background: fill,
        border: "4px double #E74C3C",
        borderRadius: "50%",
        padding: "10px 14px",
      }}
    >
      <Handle type="target" position={Position.Left} id="left" />
      <Handle type="target" position={Position.Top} id="top" />
      <div>
        {multilineLabel(d.label)}
        {d.sub_label && (
          <>
            <br />
            <span style={{ fontSize: 9, opacity: 0.8 }}>{d.sub_label}</span>
          </>
        )}
      </div>
    </div>
  );
}

// annotation — sticky note with WYSIWYG editing, resizable, connectable handles on all sides

// Curated font list for diagram documentation
const FONTS = [
  { label: "Helvetica", value: "Helvetica, Arial, sans-serif" },
  { label: "Georgia", value: "Georgia, serif" },
  { label: "Verdana", value: "Verdana, sans-serif" },
  { label: "Trebuchet MS", value: "'Trebuchet MS', sans-serif" },
  { label: "Courier New", value: "'Courier New', monospace" },
];
const DEFAULT_FONT = FONTS[0].value;

const FONT_SIZES = [9, 10, 11, 12, 14, 16, 18, 24];
const DEFAULT_FONT_SIZE = "12";

// Minimal inline font-size extension (adds fontSize attribute to the textStyle mark)
const FontSizeExtension = Extension.create({
  name: "fontSize",
  addGlobalAttributes() {
    return [
      {
        types: ["textStyle"],
        attributes: {
          fontSize: {
            default: null,
            parseHTML: (el) => el.style.fontSize?.replace(/px$/, "") || null,
            renderHTML: (attrs) =>
              attrs.fontSize ? { style: `font-size: ${attrs.fontSize}px` } : {},
          },
        },
      },
    ];
  },
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  addCommands(): any {
    return {
      setFontSize: (size: string) => ({ chain }: { chain: () => any }) =>
        chain().setMark("textStyle", { fontSize: size }).run(),
    };
  },
});

export type AnnotationStyle = {
  noFill?: boolean;
  borderStyle?: "dashed" | "solid" | "dotted" | "none";
  borderColor?: string;
};

type AnnotationToolbarProps = {
  editor: ReturnType<typeof useEditor>;
  onImageFile: () => void;
  annotationStyle: AnnotationStyle;
  onAnnotationStyleChange: (patch: Partial<AnnotationStyle>) => void;
};

function AnnotationToolbar({ editor, onImageFile, annotationStyle, onAnnotationStyleChange }: AnnotationToolbarProps) {
  if (!editor) return null;

  const btnStyle = (active: boolean): React.CSSProperties => ({
    fontWeight: active ? "bold" : "normal",
    fontStyle: "normal",
    background: active ? "#ffe082" : "transparent",
    border: "1px solid #ccc",
    borderRadius: 3,
    padding: "1px 6px",
    fontSize: 11,
    cursor: "pointer",
    lineHeight: "18px",
    color: "#333",
    flexShrink: 0,
  });

  const selectStyle: React.CSSProperties = {
    fontSize: 11,
    border: "1px solid #ccc",
    borderRadius: 3,
    padding: "1px 2px",
    cursor: "pointer",
    background: "transparent",
    color: "#333",
    maxWidth: 100,
  };

  const activeFont = editor.getAttributes("textStyle").fontFamily ?? DEFAULT_FONT;
  const activeFontSize = editor.getAttributes("textStyle").fontSize ?? DEFAULT_FONT_SIZE;

  return (
    <div
      className="nodrag nopan nowheel"
      style={{
        display: "flex",
        alignItems: "center",
        gap: 3,
        marginBottom: 4,
        paddingBottom: 4,
        borderBottom: "1px solid #F9A825",
        flexShrink: 0,
        flexWrap: "wrap",
      }}
    >
      <button
        style={btnStyle(editor.isActive("bold"))}
        onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().toggleBold().run(); }}
        title="Bold"
      >
        <strong>B</strong>
      </button>
      <button
        style={btnStyle(editor.isActive("italic"))}
        onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().toggleItalic().run(); }}
        title="Italic"
      >
        <em>I</em>
      </button>
      <button
        style={btnStyle(editor.isActive("bulletList"))}
        onMouseDown={(e) => { e.preventDefault(); editor.chain().focus().toggleBulletList().run(); }}
        title="Bullet list"
      >
        &#8226;&#8212;
      </button>
      <button
        style={btnStyle(false)}
        onMouseDown={(e) => { e.preventDefault(); onImageFile(); }}
        title="Upload image"
      >
        &#128247;
      </button>

      <select
        style={selectStyle}
        value={activeFont}
        title="Font"
        onChange={(e) => {
          editor.chain().focus().setFontFamily(e.target.value).run();
        }}
      >
        {FONTS.map((f) => (
          <option key={f.value} value={f.value}>{f.label}</option>
        ))}
      </select>

      <select
        style={{ ...selectStyle, maxWidth: 52 }}
        value={String(activeFontSize)}
        title="Size"
        onChange={(e) => {
          // eslint-disable-next-line @typescript-eslint/no-explicit-any
          (editor.chain().focus() as any).setFontSize(e.target.value).run();
        }}
      >
        {FONT_SIZES.map((s) => (
          <option key={s} value={String(s)}>{s}</option>
        ))}
      </select>

      {/* Appearance divider */}
      <div style={{ width: 1, height: 16, background: "#ddd", flexShrink: 0, margin: "0 2px" }} />

      {/* No fill toggle */}
      <button
        style={btnStyle(annotationStyle.noFill ?? false)}
        title="No fill (transparent background)"
        onMouseDown={(e) => { e.preventDefault(); onAnnotationStyleChange({ noFill: !(annotationStyle.noFill ?? false) }); }}
      >
        &#9635;
      </button>

      {/* Border style */}
      <select
        style={selectStyle}
        value={annotationStyle.borderStyle ?? "dashed"}
        title="Border style"
        onChange={(e) => onAnnotationStyleChange({ borderStyle: e.target.value as AnnotationStyle["borderStyle"] })}
      >
        <option value="dashed">Dashed</option>
        <option value="solid">Solid</option>
        <option value="dotted">Dotted</option>
        <option value="none">No border</option>
      </select>

      {/* Border color — hidden when border is off */}
      {(annotationStyle.borderStyle ?? "dashed") !== "none" && (
        <span
          style={{
            width: 16,
            height: 16,
            borderRadius: 3,
            border: "1px solid #aaa",
            background: annotationStyle.borderColor ?? "#F9A825",
            display: "inline-block",
            flexShrink: 0,
            cursor: "pointer",
            position: "relative",
          }}
          title="Border color"
        >
          <input
            type="color"
            value={annotationStyle.borderColor ?? "#F9A825"}
            onChange={(e) => onAnnotationStyleChange({ borderColor: e.target.value })}
            style={{ opacity: 0, position: "absolute", inset: 0, width: "100%", height: "100%", cursor: "pointer", padding: 0, border: "none" }}
          />
        </span>
      )}
    </div>
  );
}

export function AnnotationNode({ data, id, selected }: NodeProps) {
  const d = data as { text?: string; colors?: NodeColors; annotationStyle?: AnnotationStyle };
  const annStyle: AnnotationStyle = d.annotationStyle ?? {};
  const fill = annStyle.noFill ? "transparent" : (d.colors?.annotation ?? DEFAULT_NODE_COLORS.annotation);
  const borderStyle = annStyle.borderStyle ?? "dashed";
  const borderColor = annStyle.borderColor ?? "#F9A825";
  const border = borderStyle === "none" ? "none" : `2px ${borderStyle} ${borderColor}`;
  const [editing, setEditing] = useState(false);
  const { updateNodeData } = useReactFlow();

  const handleAnnotationStyleChange = (patch: Partial<AnnotationStyle>) => {
    updateNodeData(id, { annotationStyle: { ...annStyle, ...patch } });
  };
  const imageFileInputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const blurTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const commitAndExit = (e: ReturnType<typeof useEditor>) => {
    updateNodeData(id, { text: e.getHTML() });
    setEditing(false);
  };

  const editor = useEditor({
    extensions: [
      StarterKit,
      TiptapImage.configure({ inline: false }),
      TextStyle,
      FontFamily,
      FontSizeExtension,
    ],
    content: d.text || "",
    editable: false,
    onFocus: () => {
      if (blurTimerRef.current) {
        clearTimeout(blurTimerRef.current);
        blurTimerRef.current = null;
      }
    },
    onBlur: ({ editor: e }) => {
      // Delay exit so focus can return from toolbar selects without flicker
      blurTimerRef.current = setTimeout(() => {
        if (containerRef.current?.contains(document.activeElement)) return;
        commitAndExit(e);
      }, 150);
    },
  });

  // Clean up blur timer on unmount
  useEffect(() => {
    return () => { if (blurTimerRef.current) clearTimeout(blurTimerRef.current); };
  }, []);

  // Sync external text changes into editor when not editing
  useEffect(() => {
    if (editor && !editing) {
      const next = d.text || "";
      if (next !== editor.getHTML()) editor.commands.setContent(next);
    }
  }, [d.text, editor, editing]);

  // Toggle editable and auto-focus when editing state changes
  useEffect(() => {
    if (!editor) return;
    editor.setEditable(editing);
    if (editing) editor.commands.focus("end");
  }, [editing, editor]);

  const handleImageFile = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = () => {
      if (typeof reader.result === "string")
        editor?.chain().focus().setImage({ src: reader.result }).run();
    };
    reader.readAsDataURL(file);
    e.target.value = "";
  };

  return (
    <div
      ref={containerRef}
      onDoubleClick={(e) => { e.stopPropagation(); setEditing(true); }}
      style={{
        background: fill,
        border,
        borderRadius: 6,
        padding: "8px 10px",
        minWidth: 140,
        minHeight: 60,
        width: "100%",
        height: "100%",
        display: "flex",
        flexDirection: "column",
        position: "relative",
        boxShadow: "0 1px 4px rgba(0,0,0,0.12)",
        boxSizing: "border-box",
      }}
    >
      <NodeResizer
        minWidth={140}
        minHeight={60}
        isVisible={selected}
        lineStyle={{ borderColor }}
        handleStyle={{ borderColor, background: "#fff" }}
      />
      <Handle type="source" position={Position.Top} id="top" />
      <Handle type="source" position={Position.Right} id="right" />
      <Handle type="source" position={Position.Bottom} id="bottom" />
      <Handle type="source" position={Position.Left} id="left" />

      {editing && (
        <AnnotationToolbar
          editor={editor}
          onImageFile={() => imageFileInputRef.current?.click()}
          annotationStyle={annStyle}
          onAnnotationStyleChange={handleAnnotationStyleChange}
        />
      )}

      <div
        className="nodrag nopan nowheel"
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            if (editor) commitAndExit(editor);
          }
        }}
        style={{
          flex: 1,
          overflow: "auto",
          wordBreak: "break-word",
          overflowWrap: "break-word",
          fontFamily: "Helvetica, Arial, sans-serif",
          fontSize: 12,
          lineHeight: 1.4,
          color: "#333",
          position: "relative",
        }}
      >
        {editor?.isEmpty && !editing && (
          <span style={{ color: "#aaa", pointerEvents: "none", userSelect: "none" }}>
            Double-click to add note…
          </span>
        )}
        <EditorContent editor={editor} />
      </div>

      <input
        ref={imageFileInputRef}
        type="file"
        accept="image/*"
        style={{ display: "none" }}
        onChange={handleImageFile}
        className="nodrag"
      />
    </div>
  );
}

export const nodeTypes = {
  start: StartNode,
  decision: DecisionNode,
  process: ProcessNode,
  action: ActionNode,
  end: EndNode,
  annotation: AnnotationNode,
};
