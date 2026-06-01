import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import ClarifyCard from "./ClarifyCard";
import type { ClarifyData } from "../types";

const data: ClarifyData = {
  reason: "book_unknown", message: "Pick one:",
  candidates: [{ slug: "islp", name: "Intro to Statistical Learning",
                 authors_short: "James et al.", chapters: ["ch02", "ch07"] }],
  chapter_guess: "ch07", sections_guess: ["7.2", "7.3"],
};

describe("ClarifyCard", () => {
  it("renders message and a chip per candidate", () => {
    render(<ClarifyCard data={data} onPick={() => {}} />);
    expect(screen.getByText("Pick one:")).toBeInTheDocument();
    expect(screen.getByText(/Intro to Statistical Learning/)).toBeInTheDocument();
    expect(screen.getByText(/James et al\./)).toBeInTheDocument();
  });

  it("calls onPick with slug + guessed chapter/sections on click", () => {
    const onPick = vi.fn();
    render(<ClarifyCard data={data} onPick={onPick} />);
    fireEvent.click(screen.getByRole("button", { name: /Intro to Statistical Learning/ }));
    expect(onPick).toHaveBeenCalledWith("islp", "ch07", ["7.2", "7.3"]);
  });
});
