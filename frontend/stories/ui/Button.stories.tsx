import type { Meta, StoryObj } from "@storybook/react";
import { Stack } from "@mui/material";
import { Search, WarningAmber } from "@mui/icons-material";
import { Button } from "../../src/components/ui";

const meta: Meta<typeof Button> = {
  title: "Core/Button",
  component: Button,
  args: {
    children: "Run Clinical Query",
    variant: "primary",
    size: "medium",
  },
};

export default meta;

type Story = StoryObj<typeof Button>;

export const Default: Story = {};

export const Variants: Story = {
  render: () => (
    <Stack direction="row" spacing={1.2} flexWrap="wrap" useFlexGap>
      <Button variant="primary">Primary</Button>
      <Button variant="secondary">Secondary</Button>
      <Button variant="ghost">Ghost</Button>
      <Button variant="clinical" startIcon={<Search />}>
        Clinical
      </Button>
      <Button variant="danger" startIcon={<WarningAmber />}>
        Critical
      </Button>
    </Stack>
  ),
};

export const Loading: Story = {
  args: {
    loading: true,
    children: "Analyzing",
  },
};
