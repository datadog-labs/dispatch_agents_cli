import { useState, useRef, useEffect } from 'react';

const MIN_TRAY_HEIGHT = 80;
const DEFAULT_TRAY_HEIGHT = 280;
const MIN_TOP_HEIGHT = 320;

// Encapsulates the draggable output-tray logic shared by AgentDetailsPage and
// TopicDetailsPage: height state, collapse state, drag-handle event listeners
// (with unmount cleanup), and the isOverlaying computed value.
export function useDraggableTray() {
  const [trayHeight, setTrayHeight] = useState(DEFAULT_TRAY_HEIGHT);
  const [isCollapsed, setIsCollapsed] = useState(false);

  const bodyRef = useRef(null);
  const startYRef = useRef(0);
  const startHeightRef = useRef(0);
  const dragCleanupRef = useRef(null);

  // Remove listeners if the component unmounts mid-drag (e.g. user navigates away)
  useEffect(() => () => { dragCleanupRef.current?.(); }, []);

  const handleDragStart = (e) => {
    e.preventDefault();
    startYRef.current = e.clientY;
    startHeightRef.current = trayHeight;
    document.body.style.cursor = 'ns-resize';
    document.body.style.userSelect = 'none';

    const onMove = (moveEvent) => {
      const delta = startYRef.current - moveEvent.clientY;
      const maxHeight = bodyRef.current ? bodyRef.current.clientHeight - 48 : 800;
      setTrayHeight(Math.max(MIN_TRAY_HEIGHT, Math.min(maxHeight, startHeightRef.current + delta)));
    };

    const removeDragListeners = () => {
      document.body.style.cursor = '';
      document.body.style.userSelect = '';
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
      dragCleanupRef.current = null;
    };

    const onUp = () => removeDragListeners();

    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
    dragCleanupRef.current = removeDragListeners;
  };

  const handleCollapseToggle = () => setIsCollapsed(prev => !prev);

  // Read from bodyRef during render — same "stale on resize" trade-off as inline.
  // Once the tray would compress the top section below MIN_TOP_HEIGHT, it switches
  // to absolute positioning so it overlaps rather than compresses further.
  const bodyHeight = bodyRef.current?.clientHeight ?? 0;
  const isOverlaying = !isCollapsed && bodyHeight > 0 && trayHeight > bodyHeight - MIN_TOP_HEIGHT;

  return {
    trayHeight,
    isCollapsed,
    setIsCollapsed,
    bodyRef,
    handleDragStart,
    handleCollapseToggle,
    isOverlaying,
    MIN_TOP_HEIGHT,
  };
}
