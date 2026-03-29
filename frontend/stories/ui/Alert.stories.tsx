import type { Meta, StoryObj } from "@storybook/react";
import { Stack } from "@mui/material";
import { Alert } from "../../src/components/ui";

const meta: Meta<typeof Alert> = {
  title: "Core/Alert",
  component: Alert,
  args: {
    severity: "info",
    variant: "standard",
    children: "Clinical context message.",
  },
};

export default meta;

type Story = StoryObj<typeof Alert>;

export const Default: Story = {};

export const ClinicalSeveritySet: Story = {
  render: () => (
    <Stack spacing={1.2}>
      <Alert severity="error" variant="clinical" title="Major contraindication">
        Warfarin + Amiodarone requires immediate review.
      </Alert>
      <Alert severity="warning" variant="clinical" title="Moderate risk">
        Monitor INR every 48 hours for dose adjustments.
      </Alert>
      <Alert severity="info" variant="clinical" title="Minor note">
        Recommend hydration protocol while monitoring labs.
      </Alert>
      <Alert severity="success" variant="clinical" title="Validated">
        Safety checks completed with no unresolved blockers.
      </Alert>
    </Stack>
  ),
};
