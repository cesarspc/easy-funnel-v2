/** Responsive banner renderer (Requirement 4.13-4.14, 8.19-8.20). */

import type { JSX } from "react";
import "./Banner.css";

export interface BannerVariant {
  width: number;
  format: "webp" | "jpeg";
  url: string;
}

export interface BannerProps {
  /** Banner ID */
  id: number;
  /** Alternative text */
  alt_text: string;
  /** Banner order index */
  order_index: number;
  /** Image variants at different widths */
  variants: BannerVariant[];
  /** Lazy load if below fold */
  lazy?: boolean;
}

/**
 * Renders a responsive banner with WebP + JPEG fallback.
 * Uses srcset/sizes for responsive image loading.
 * Lazy loads below the fold.
 */
export function Banner({ id, alt_text, variants, lazy = true }: BannerProps): JSX.Element {
  if (variants.length === 0) {
    return <div data-test="banner-placeholder">No image variants available</div>;
  }

  // Sort variants by width ascending
  const sortedVariants = [...variants].sort((a, b) => a.width - b.width);
  const sourceWidths = sortedVariants.map((v) => `${v.url} ${v.width}w`).join(", ");

  // Get JPEG fallback (last variant in sorted list)
  const jpegFallback = sortedVariants.find((v) => v.format === "jpeg") ?? sortedVariants[sortedVariants.length - 1];

  // Get dimensions from variant URLs (extract from URL or use defaults)
  // For simplicity, we'll derive dimensions from width - in production, these would be in the API response
  const width = jpegFallback.width;
  // Calculate aspect ratio from original - simplified for demo
  const height = Math.round(width * 0.6); // Assume 5:3 aspect ratio

  return (
    <div className="banner" data-banner-id={id}>
      <picture>
        <source
          type="image/webp"
          srcSet={sourceWidths}
          sizes="(max-width: 768px) 100vw, (max-width: 1200px) 80vw, 1200px"
        />
        <img
          src={jpegFallback.url}
          alt={alt_text}
          width={width}
          height={height}
          loading={lazy ? "lazy" : "eager"}
          className="banner-image"
          decoding="async"
        />
      </picture>
      <span className="banner-alt-text" style={{ display: "none" }}>
        {alt_text}
      </span>
    </div>
  );
}
