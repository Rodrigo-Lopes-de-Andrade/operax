import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { SignedMinutes } from "@/components/ui/signed-minutes";

describe("SignedMinutes", () => {
  it("never lets colour carry the direction on its own", () => {
    render(<SignedMinutes minutes={-32} direction="shortfall" />);

    expect(screen.getByText("−32")).toBeInTheDocument();
    expect(screen.getByText("faltante")).toBeInTheDocument();
  });

  it("marks a surplus with the sign and the word", () => {
    render(<SignedMinutes minutes={41} direction="surplus" />);

    expect(screen.getByText("+41")).toBeInTheDocument();
    expect(screen.getByText("excedente")).toBeInTheDocument();
  });

  it("uses the direction of the event, not the sign of the number", () => {
    // An incomplete punch pair has no direction and no minutes; it must not be
    // read as "zero surplus".
    render(<SignedMinutes minutes={0} direction="neutral" />);

    expect(screen.getByText("sem par")).toBeInTheDocument();
  });
});
