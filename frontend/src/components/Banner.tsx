/** Responsive banner renderer (Requirement 4.13-4.14, 8.19-8.20). */

import type { JSX } from "react";
import "./Banner.css";

export interface BannerVariant {
  width: number;
  height: number;
  format: "webp" | "jpeg";
  url: string;
}

const BANNER_SIZES = "(max-width: 640px) 100vw, 640px";

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

  // Keep each format in its own candidate set: a <source type="image/webp">
  // must never advertise JPEG URLs with duplicate width descriptors.
  const sortedVariants = [...variants].sort((a, b) => a.width - b.width);
  const webpVariants = sortedVariants.filter((variant) => variant.format === "webp");
  const jpegVariants = sortedVariants.filter((variant) => variant.format === "jpeg");
  const webpSrcSet = webpVariants.map((variant) => `${variant.url} ${variant.width}w`).join(", ");
  const jpegSrcSet = jpegVariants.map((variant) => `${variant.url} ${variant.width}w`).join(", ");

  // The largest JPEG is the non-picture fallback. Every generated candidate
  // has the same aspect ratio, so its stored dimensions reserve the right
  // amount of space before any candidate finishes decoding.
  const fallback = jpegVariants[jpegVariants.length - 1] ?? sortedVariants[sortedVariants.length - 1];

  return (
    <div className="banner" data-banner-id={id}>
      <picture>
        {webpSrcSet && <source type="image/webp" srcSet={webpSrcSet} sizes={BANNER_SIZES} />}
        <img
          src={fallback.url}
          srcSet={jpegSrcSet || undefined}
          sizes={jpegSrcSet ? BANNER_SIZES : undefined}
          alt={alt_text}
          width={fallback.width}
          height={fallback.height}
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
