-- AlterTable
ALTER TABLE "image_assets" ADD COLUMN     "top_edge_color" VARCHAR(7),
ADD COLUMN     "bottom_edge_color" VARCHAR(7),
ADD COLUMN     "top_edge_flat" BOOLEAN NOT NULL DEFAULT false,
ADD COLUMN     "bottom_edge_flat" BOOLEAN NOT NULL DEFAULT false;
