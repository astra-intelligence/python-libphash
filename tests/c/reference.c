/* The C side of the binding's parity tests: libphash called directly, with no Python
 * in between, so that tests/test_c_parity.py can require the binding to give the same
 * values byte for byte.
 *
 * It reads one job per line from stdin, fields separated by tabs:
 *
 *     file    <path>                                 [setting=value ...]
 *     memory  <path>                                 [setting=value ...]
 *     pixels  <path> <width> <height> <channels> <stride> [setting=value ...]
 *
 * "file" loads with ph_load_from_file(), "memory" reads the file and loads it with
 * ph_load_from_memory(), "pixels" reads raw 8-bit pixels and loads them with
 * ph_load_from_pixels(). A setting is a field of the binding's Config and its value as
 * Python prints it (gray_weights=38,75,15, whash_mode=full, grayscale=1); each is
 * applied with its own ph_context_set_*() call, in the order given.
 *
 * A line "build_info" instead prints ph_get_build_info(), by which the tests check that
 * the program and the extension link the same build.
 *
 * It writes one line per job: "config <code>" when a setting is refused, "load <code>"
 * when the load fails, and otherwise one field per algorithm in ph_algorithm_t order,
 * each from the algorithm's own ph_compute_*() function: 16 hex digits for a 64-bit
 * hash, "<kind>:<hex>" for a digest, "!<code>" for an error. */

#include <libphash.h>

#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define MAX_LINE 8192
#define MAX_FIELDS 64

static void fail(const char *what, const char *detail) {
    fprintf(stderr, "reference: %s: %s\n", what, detail);
    exit(2);
}

static uint8_t *read_file(const char *path, size_t *out_len) {
    FILE *f = fopen(path, "rb");
    if (!f)
        fail("cannot open", path);
    uint8_t *buf = NULL;
    size_t len = 0, cap = 0;
    for (;;) {
        if (len == cap) {
            cap = cap ? cap * 2 : 65536;
            buf = (uint8_t *)realloc(buf, cap);
            if (!buf)
                fail("out of memory reading", path);
        }
        size_t n = fread(buf + len, 1, cap - len, f);
        len += n;
        if (n == 0)
            break;
    }
    if (ferror(f))
        fail("cannot read", path);
    fclose(f);
    *out_len = len;
    return buf;
}

static int to_int(const char *text) {
    char *end;
    long v = strtol(text, &end, 10);
    if (*text == '\0' || *end != '\0')
        fail("not an integer", text);
    return (int)v;
}

/* Parsed as a double and narrowed, as cffi narrows a Python float for a float
 * parameter. */
static float to_float(const char *text) {
    char *end;
    double v = strtod(text, &end);
    if (*text == '\0' || *end != '\0')
        fail("not a number", text);
    return (float)v;
}

static int value_of(const char *text, const char *const names[], const int values[],
                    size_t n) {
    for (size_t i = 0; i < n; i++)
        if (strcmp(text, names[i]) == 0)
            return values[i];
    fail("unknown value", text);
    return 0;
}

static ph_error_t apply(ph_context_t *ctx, char *setting) {
    char *eq = strchr(setting, '=');
    if (!eq)
        fail("setting without a value", setting);
    *eq = '\0';
    const char *key = setting;
    char *value = eq + 1;
    /* A comma-separated value: up to three numbers. */
    char *parts[3] = {value, NULL, NULL};
    for (int i = 1; i < 3 && parts[i - 1]; i++) {
        char *comma = strchr(parts[i - 1], ',');
        if (comma) {
            *comma = '\0';
            parts[i] = comma + 1;
        }
    }

    if (strcmp(key, "gamma") == 0)
        return ph_context_set_gamma(ctx, to_float(value));
    if (strcmp(key, "gray_weights") == 0) {
        if (!parts[1] || !parts[2])
            fail("gray_weights needs three values", value);
        return ph_context_set_gray_weights(ctx, to_int(parts[0]), to_int(parts[1]),
                                           to_int(parts[2]));
    }
    if (strcmp(key, "phash") == 0) /* dct_size,reduction_size */
        return ph_context_set_phash_params(ctx, to_int(parts[0]), to_int(parts[1]));
    if (strcmp(key, "radial") == 0) /* projections,samples,sigma */
        return ph_context_set_radial_params(ctx, to_int(parts[0]), to_int(parts[1]),
                                            to_float(parts[2]));
    if (strcmp(key, "bmh_block_size") == 0)
        return ph_context_set_block_params(ctx, to_int(value));
    if (strcmp(key, "mhash") == 0) /* alpha,level,size */
        return ph_context_set_mhash_params(ctx, to_float(parts[0]), to_float(parts[1]),
                                           to_int(parts[2]));
    if (strcmp(key, "whash_mode") == 0) {
        static const char *const names[] = {"fast", "full"};
        static const int values[] = {PH_WHASH_FAST, PH_WHASH_FULL};
        return ph_context_set_whash_mode(ctx, (ph_whash_mode_t)value_of(value, names, values, 2));
    }
    if (strcmp(key, "whash_remove_max_haar_ll") == 0)
        return ph_context_set_whash_remove_max_haar_ll(ctx, to_int(value));
    if (strcmp(key, "grayscale") == 0)
        return ph_context_set_load_grayscale(ctx, to_int(value));
    if (strcmp(key, "alpha_mode") == 0) {
        static const char *const names[] = {"grey", "white", "black", "ignore"};
        static const int values[] = {PH_ALPHA_BLEND_GREY, PH_ALPHA_BLEND_WHITE,
                                     PH_ALPHA_BLEND_BLACK, PH_ALPHA_IGNORE};
        return ph_context_set_alpha_mode(ctx, (ph_alpha_mode_t)value_of(value, names, values, 4));
    }
    if (strcmp(key, "auto_orient") == 0)
        return ph_context_set_auto_orient(ctx, to_int(value));
    if (strcmp(key, "max_pixels") == 0) {
        char *end;
        unsigned long long v = strtoull(value, &end, 10);
        if (*value == '\0' || *end != '\0')
            fail("not an integer", value);
        return ph_context_set_max_pixels(ctx, (uint64_t)v);
    }
    if (strcmp(key, "decode_scale") == 0) {
        static const char *const names[] = {"1", "2", "4", "8"};
        static const int values[] = {PH_DECODE_SCALE_FULL, PH_DECODE_SCALE_HALF,
                                     PH_DECODE_SCALE_QUARTER, PH_DECODE_SCALE_EIGHTH};
        return ph_context_set_decode_scale(ctx,
                                           (ph_decode_scale_t)value_of(value, names, values, 4));
    }
    fail("unknown setting", key);
    return PH_SUCCESS;
}

typedef ph_error_t (*uint64_fn)(ph_context_t *, uint64_t *);
typedef ph_error_t (*digest_fn)(ph_context_t *, ph_digest_t *);

static void print_hashes(ph_context_t *ctx) {
    /* In ph_algorithm_t order; the first four give a uint64_t. */
    static const uint64_fn uint64_fns[] = {ph_compute_ahash, ph_compute_dhash,
                                           ph_compute_phash, ph_compute_whash};
    static const digest_fn digest_fns[] = {ph_compute_bmh, ph_compute_mhash,
                                           ph_compute_radial_hash, ph_compute_color_hash,
                                           ph_compute_color_moments_hash};
    for (int a = 0; a < PH_ALGORITHM_COUNT; a++) {
        if (a > 0)
            putchar(' ');
        ph_error_t err;
        if (a < 4) {
            uint64_t h = 0;
            err = uint64_fns[a](ctx, &h);
            if (err == PH_SUCCESS) {
                printf("%016" PRIx64, h);
                continue;
            }
        } else {
            ph_digest_t d;
            memset(&d, 0, sizeof d);
            err = digest_fns[a - 4](ctx, &d);
            if (err == PH_SUCCESS) {
                printf("%d:", d.kind);
                for (int i = 0; i < d.size; i++)
                    printf("%02x", d.data[i]);
                continue;
            }
        }
        printf("!%d", (int)err);
    }
    putchar('\n');
}

static void run(char *line) {
    char *fields[MAX_FIELDS];
    int n = 0;
    for (char *tok = strtok(line, "\t"); tok; tok = strtok(NULL, "\t")) {
        if (n == MAX_FIELDS)
            fail("too many fields", fields[0]);
        fields[n++] = tok;
    }
    if (n < 2)
        fail("a job needs a source and a path", n ? fields[0] : "");

    const char *source = fields[0];
    const char *path = fields[1];
    int first_setting = strcmp(source, "pixels") == 0 ? 6 : 2;
    if (n < first_setting)
        fail("pixels needs width, height, channels and stride", path);

    ph_context_t *ctx = NULL;
    if (ph_create(&ctx) != PH_SUCCESS)
        fail("ph_create failed", path);
    for (int i = first_setting; i < n; i++) {
        ph_error_t err = apply(ctx, fields[i]);
        if (err != PH_SUCCESS) {
            printf("config %d\n", (int)err);
            ph_free(ctx);
            return;
        }
    }

    ph_error_t err;
    if (strcmp(source, "file") == 0) {
        err = ph_load_from_file(ctx, path);
    } else {
        size_t len = 0;
        uint8_t *buf = read_file(path, &len);
        if (strcmp(source, "memory") == 0)
            err = ph_load_from_memory(ctx, buf, len);
        else if (strcmp(source, "pixels") == 0)
            err = ph_load_from_pixels(ctx, buf, to_int(fields[2]), to_int(fields[3]),
                                      to_int(fields[4]), to_int(fields[5]));
        else
            fail("unknown source", source);
        free(buf);
    }
    if (err != PH_SUCCESS)
        printf("load %d\n", (int)err);
    else
        print_hashes(ctx);
    ph_free(ctx);
}

int main(void) {
    static char line[MAX_LINE];
    while (fgets(line, sizeof line, stdin)) {
        size_t len = strlen(line);
        if (len && line[len - 1] != '\n' && !feof(stdin))
            fail("line too long", line);
        while (len && (line[len - 1] == '\n' || line[len - 1] == '\r'))
            line[--len] = '\0';
        if (strcmp(line, "build_info") == 0)
            printf("%s\n", ph_get_build_info());
        else if (len)
            run(line);
    }
    fflush(stdout);
    return ferror(stdout) ? 1 : 0;
}
