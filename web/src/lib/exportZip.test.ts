import { describe, it, expect } from "vitest";
import { extractImageUrls, imageFilename } from "./exportZip";

describe("extractImageUrls", () => {
  it("extracts /api, /img and http(s) image links", () => {
    const md = [
      "![a](/api/figures?path=x.jpg)",
      "![b](/img/fig.png)",
      "![c](https://example.com/p.png)",
    ].join("\n\n");
    expect(extractImageUrls(md)).toEqual([
      "/api/figures?path=x.jpg",
      "/img/fig.png",
      "https://example.com/p.png",
    ]);
  });

  it("dedupes a repeated url, first-seen order", () => {
    const md = "![a](/img/x.png)\n\n![again](/img/x.png)\n\n![b](/img/y.png)";
    expect(extractImageUrls(md)).toEqual(["/img/x.png", "/img/y.png"]);
  });

  it("ignores plain links and data URIs", () => {
    const md = "[text](/api/foo) and ![d](data:image/png;base64,AAAA)";
    expect(extractImageUrls(md)).toEqual([]);
  });

  it("extracts the url when an image has a title attribute", () => {
    expect(extractImageUrls('![a](/img/x.png "a title")')).toEqual(["/img/x.png"]);
  });
});

describe("imageFilename", () => {
  it("uses the url basename + a stable short hash + extension", () => {
    const a = imageFilename("/img/scatter.png");
    expect(a).toMatch(/^scatter-[a-z0-9]+\.png$/);
    expect(imageFilename("/img/scatter.png")).toBe(a);
  });

  it("derives extension from content type when url has none", () => {
    expect(imageFilename("/api/figures?path=x", "image/jpeg")).toMatch(/\.jpg$/);
  });

  it("falls back to figure + img extension", () => {
    expect(imageFilename("/api/figures?path=")).toMatch(/^figure-[a-z0-9]+\.img$/);
  });

  it("different urls with same basename get different names", () => {
    const a = imageFilename("/a/fig.png");
    const b = imageFilename("/b/fig.png");
    expect(a).not.toBe(b);
  });

  it("takes only the basename of a slash-containing path param", () => {
    const url = "/api/figures?path=%2Fhome%2Fiohan%2FRAG%2Fmedia%2Fimage_rsrcD3S.jpg";
    expect(imageFilename(url)).toMatch(/^image_rsrcD3S-[a-z0-9]+\.jpg$/);
  });
});
