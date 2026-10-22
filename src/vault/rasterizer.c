/* Orthographic triangle rasterization matching render.py's Python fallback.
 * All arrays are contiguous: xy[N][2], z[N], faces[F][3], colors[F][3].
 * Callers initialize depth to -INFINITY and pixels to the background color.
 */
#include <math.h>
#include <stddef.h>
#include <stdint.h>

void vault_rasterize(
    const double *xy, const double *z, const int64_t *faces,
    const int64_t *visible, const uint8_t *colors, size_t visible_count,
    int width, int height, uint8_t *pixels, double *depth)
{
    for (size_t n = 0; n < visible_count; ++n) {
        const int64_t face = visible[n];
        const int64_t ia = faces[3 * face];
        const int64_t ib = faces[3 * face + 1];
        const int64_t ic = faces[3 * face + 2];
        const double ax = xy[2 * ia], ay = xy[2 * ia + 1];
        const double bx = xy[2 * ib], by = xy[2 * ib + 1];
        const double cx = xy[2 * ic], cy = xy[2 * ic + 1];
        const double determinant = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy);
        if (fabs(determinant) < 1e-12)
            continue;
        const int x0 = (int)fmax(0.0, floor(fmin(fmin(ax, bx), cx)));
        const int y0 = (int)fmax(0.0, floor(fmin(fmin(ay, by), cy)));
        const int x1 = (int)fmin(width - 1.0, ceil(fmax(fmax(ax, bx), cx)));
        const int y1 = (int)fmin(height - 1.0, ceil(fmax(fmax(ay, by), cy)));
        const double za = z[ia], zb = z[ib], zc = z[ic];
        for (int py = y0; py <= y1; ++py) {
            const double y = py + 0.5;
            for (int px = x0; px <= x1; ++px) {
                const double x = px + 0.5;
                const double u = ((by - cy) * (x - cx) + (cx - bx) * (y - cy)) / determinant;
                const double v = ((cy - ay) * (x - cx) + (ax - cx) * (y - cy)) / determinant;
                const double w = 1.0 - u - v;
                const double value = u * za + v * zb + w * zc;
                const size_t pixel = (size_t)py * (size_t)width + (size_t)px;
                if (u >= -1e-8 && v >= -1e-8 && w >= -1e-8 && value > depth[pixel]) {
                    depth[pixel] = value;
                    pixels[3 * pixel] = colors[3 * face];
                    pixels[3 * pixel + 1] = colors[3 * face + 1];
                    pixels[3 * pixel + 2] = colors[3 * face + 2];
                }
            }
        }
    }
}
