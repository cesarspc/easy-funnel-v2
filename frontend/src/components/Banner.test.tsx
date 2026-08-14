import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { Banner } from "./Banner";

describe("Banner", () => {
  it("keeps WebP and JPEG candidates separate and advertises the 640px page width", () => {
    const { container } = render(
      <Banner
        id={1}
        alt_text="Producto vertical"
        order_index={0}
        lazy={false}
        variants={[
          { width: 1200, height: 1800, format: "jpeg", url: "/1200.jpg" },
          { width: 480, height: 720, format: "webp", url: "/480.webp" },
          { width: 480, height: 720, format: "jpeg", url: "/480.jpg" },
          { width: 1200, height: 1800, format: "webp", url: "/1200.webp" },
        ]}
      />,
    );

    const source = container.querySelector("source");
    const image = screen.getByRole("img", { name: "Producto vertical" });

    expect(source).toHaveAttribute("srcset", "/480.webp 480w, /1200.webp 1200w");
    expect(source).toHaveAttribute("sizes", "(max-width: 640px) 100vw, 640px");
    expect(image).toHaveAttribute("srcset", "/480.jpg 480w, /1200.jpg 1200w");
    expect(image).toHaveAttribute("sizes", "(max-width: 640px) 100vw, 640px");
    expect(image).toHaveAttribute("src", "/1200.jpg");
    expect(image).toHaveAttribute("width", "1200");
    expect(image).toHaveAttribute("height", "1800");
  });
});
