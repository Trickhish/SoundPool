import { Directive, EventEmitter, HostListener, Output } from '@angular/core';

export interface PressPoint { x: number; y: number; }

/**
 * Emits `press` on a long-press (touch, ~500ms) or a right-click (desktop
 * contextmenu). Used to open an "add to queue / play next" menu on song rows.
 */
@Directive({ selector: '[appLongPress]', standalone: true })
export class LongPressDirective {
  @Output() press = new EventEmitter<PressPoint>();

  private timer: any = null;
  private sx = 0;
  private sy = 0;

  @HostListener('touchstart', ['$event'])
  onTouchStart(e: TouchEvent) {
    const t = e.touches[0];
    this.sx = t.clientX; this.sy = t.clientY;
    this.clear();
    this.timer = setTimeout(() => {
      this.timer = null;
      this.press.emit({ x: this.sx, y: this.sy });
    }, 500);
  }

  @HostListener('touchmove', ['$event'])
  onTouchMove(e: TouchEvent) {
    const t = e.touches[0];
    if (Math.abs(t.clientX - this.sx) > 10 || Math.abs(t.clientY - this.sy) > 10) this.clear();
  }

  @HostListener('touchend')
  @HostListener('touchcancel')
  onTouchEnd() { this.clear(); }

  @HostListener('contextmenu', ['$event'])
  onContextMenu(e: MouseEvent) {
    e.preventDefault();
    this.press.emit({ x: e.clientX, y: e.clientY });
  }

  /** True if a long-press just fired, so the caller can swallow the tap-to-add. */
  fired = false;
  private clear() {
    if (this.timer) { clearTimeout(this.timer); this.timer = null; }
  }
}
