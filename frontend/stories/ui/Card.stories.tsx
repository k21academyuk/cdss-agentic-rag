import type { Meta, StoryObj } from "@storybook/react";
import { Stack, Typography } from "@mui/material";
import { Button, Card } from "../../src/components/ui";

const meta: Meta<typeof Card> = {
  title: "Core/Card",
  component: Card,
  args: {
    variant: "default",
    children: (
      <Typography variant="body2">
        Clinical card content with token-driven spacing, radius, and elevation.
      </Typography>
    ),
  },
};

export default meta;

type Story = StoryObj<typeof Card>;

export const Default: Story = {};

export const Variants: Story = {
  render: () => (
    <Stack spacing={2}>
      <Card variant="default">
        <Typography variant="body2">Default card</Typography>
      </Card>
      <Card variant="elevated" hoverable>
        <Typography variant="body2">Elevated hoverable card</Typography>
      </Card>
      <Card variant="outlined">
        <Typography variant="body2">Outlined card</Typography>
      </Card>
      <Card variant="clinical" accentColor="#DC2626">
        <Typography variant="body2">Clinical card with alert accent</Typography>
      </Card>
    </Stack>
  ),
};

export const WithHeaderAndFooter: Story = {
  render: () => (
    <Card
      header={<Typography variant="subtitle2">Safety Highlights</Typography>}
      footer={<Button variant="secondary">Review</Button>}
    >
      <Typography variant="body2">2 major contraindications and 1 unresolved guardrail flag.</Typography>
    </Card>
  ),
};
