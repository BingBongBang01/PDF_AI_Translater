export interface M3Palette {
  primary: string;
  primaryContainer: string;
  surfaceTint: string;
  onSurface: string;
  surfaceVariant: string;
}

export class M3ThemeGenerator {
  public static hexToRgb(hex: string): { r: number; g: number; b: number } {
    let cleanHex = hex.replace('#', '');
    if (cleanHex.length === 3) {
      cleanHex = cleanHex.split('').map((c) => c + c).join('');
    }
    const num = parseInt(cleanHex, 16);
    return {
      r: (num >> 16) & 255,
      g: (num >> 8) & 255,
      b: num & 255,
    };
  }

  public static rgbToHex(r: number, g: number, b: number): string {
    const toHex = (c: number) => Math.max(0, Math.min(255, Math.round(c))).toString(16).padStart(2, '0');
    return `#${toHex(r)}${toHex(g)}${toHex(b)}`;
  }

  public static getLuminance(r: number, g: number, b: number): number {
    const a = [r, g, b].map((v) => {
      const s = v / 255;
      return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
    });
    return a[0] * 0.2126 + a[1] * 0.7152 + a[2] * 0.0722;
  }

  public static getContrastRatio(hex1: string, hex2: string): number {
    const rgb1 = this.hexToRgb(hex1);
    const rgb2 = this.hexToRgb(hex2);
    const l1 = this.getLuminance(rgb1.r, rgb1.g, rgb1.b);
    const l2 = this.getLuminance(rgb2.r, rgb2.g, rgb2.b);
    const brightest = Math.max(l1, l2);
    const darkest = Math.min(l1, l2);
    return (brightest + 0.05) / (darkest + 0.05);
  }

  public static ensureAAContrast(fgHex: string, bgHex: string): string {
    if (this.getContrastRatio(fgHex, bgHex) >= 4.5) {
      return fgHex;
    }
    const bgRgb = this.hexToRgb(bgHex);
    const bgLum = this.getLuminance(bgRgb.r, bgRgb.g, bgRgb.b);
    return bgLum > 0.5 ? '#1C1B1F' : '#E6E1E5';
  }

  public static generatePalette(seedHex: string, isDark: boolean = false): M3Palette {
    const primary = seedHex;
    const surfaceTint = primary;

    let primaryContainer: string;
    let onSurface: string;
    let surfaceVariant: string;

    if (isDark) {
      primaryContainer = '#4F378B';
      onSurface = '#E6E1E5';
      surfaceVariant = '#49454F';
    } else {
      primaryContainer = '#EADDFF';
      onSurface = '#1C1B1F';
      surfaceVariant = '#E7E0EC';
    }

    onSurface = this.ensureAAContrast(onSurface, isDark ? '#1C1B1F' : '#FEF7FF');

    return {
      primary,
      primaryContainer,
      surfaceTint,
      onSurface,
      surfaceVariant,
    };
  }

  public static applyTheme(seedHex: string, isDark: boolean = false): void {
    const palette = this.generatePalette(seedHex, isDark);
    const root = document.documentElement;

    root.style.setProperty('--md-sys-color-primary', palette.primary);
    root.style.setProperty('--md-sys-color-primary-container', palette.primaryContainer);
    root.style.setProperty('--md-sys-color-surface-tint', palette.surfaceTint);
    root.style.setProperty('--md-sys-color-on-surface', palette.onSurface);
    root.style.setProperty('--md-sys-color-surface-variant', palette.surfaceVariant);

    root.style.setProperty('--md-sys-elevation-level0', '0%');
    root.style.setProperty('--md-sys-elevation-level1', '5%');
    root.style.setProperty('--md-sys-elevation-level2', '8%');
    root.style.setProperty('--md-sys-elevation-level3', '11%');
    root.style.setProperty('--md-sys-elevation-level4', '12%');
    root.style.setProperty('--md-sys-elevation-level5', '14%');
  }
}

export const M3ComponentStyles = {
  DropdownMenu: {
    container: 'relative w-full',
    input: 'w-full rounded-xl px-4 py-3 bg-[var(--md-sys-color-surface-variant)] text-[var(--md-sys-color-on-surface)] border-none outline-none focus:ring-2 focus:ring-[var(--md-sys-color-primary)] transition-all',
    list: 'absolute z-50 w-full mt-2 rounded-2xl bg-[var(--md-sys-color-surface-variant)] text-[var(--md-sys-color-on-surface)] shadow-lg overflow-hidden py-2',
    item: 'px-4 py-3 hover:bg-[var(--md-sys-color-primary-container)] cursor-pointer transition-colors',
  },
  MediumTopAppBar: {
    header: 'sticky top-0 z-40 w-full transition-colors duration-200 bg-transparent data-[scrolled=true]:bg-[var(--md-sys-color-surface-tint)] data-[scrolled=true]:bg-opacity-8',
    title: 'text-2xl font-normal px-4 py-4 text-[var(--md-sys-color-on-surface)] transition-all data-[scrolled=true]:text-xl',
  },
  FilledButton: 'px-6 py-3 rounded-full bg-[var(--md-sys-color-primary)] text-white font-medium hover:bg-opacity-90 active:bg-opacity-80 transition-all flat',
  TonalButton: 'px-6 py-3 rounded-full bg-[var(--md-sys-color-primary-container)] text-[var(--md-sys-color-on-surface)] font-medium hover:bg-opacity-90 active:bg-opacity-80 transition-all flat',
};
