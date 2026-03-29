import type { Meta, StoryObj } from "@storybook/react";
import { Stack } from "@mui/material";
import { Chip, SeverityChip } from "../../src/components/ui";

const meta: Meta<typeof Chip> = {
  title: "Core/Chip",
  component: Chip,
  args: {
    label: "Type 2 Diabetes",
    color: "primary",
    variant: "outlined",
  },
};

export default meta;

type Story = StoryObj<typeof Chip>;

export const Default: Story = {};

export const ClinicalLabels: Story = {
  render: () => (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      <Chip label="CKD Stage 3" color="warning" />
      <Chip label="Allergy: Penicillin" color="error" variant="outlined" />
      <Chip label="HbA1c > 8%" color="info" />
      <Chip label="Validated Protocol" color="success" />
    </Stack>
  ),
};

export const SeverityLegend: Story = {
  render: () => (
    <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
      <SeverityChip severity="major" label="Major" />
      <SeverityChip severity="moderate" label="Moderate" />
      <SeverityChip severity="minor" label="Minor" />
      <SeverityChip severity="none" label="None" />
    </Stack>
  ),
};
