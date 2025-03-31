/* SPDX-License-Identifier: BSD-2-Clause
 *
 * LitePCIe fir
 *
 * This file is part of LitePCIe.
 *
 * Copyright (C) 2018-2025 / EnjoyDigital  / florent@enjoy-digital.fr
 *
 */

#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
#include <inttypes.h>
#include <unistd.h>
#include <fcntl.h>
#include <signal.h>
#include "liblitepcie.h"

/* Variables */
/*-----------*/

static char litepcie_device[1024];
static int litepcie_device_num;

/* FIR Coefficients */

static void fir_coefficients_write(const char *filename)
{
    int fd;
    FILE *fd_coefficients;
    int i;
    long coeffs_file_len;

    fd = open(litepcie_device, O_RDWR);
    if (fd < 0) {
        fprintf(stderr, "Could not init driver %s\n", litepcie_device);
        exit(1);
    }

    printf("\e[1m[> Fir Coefficients Configuration:\e[0m\n");
    printf("-------------------------\n");

    fd_coefficients = fopen(filename, "r");
    if (!fd_coefficients) {
        fprintf(stderr, "Could not coefficients file %sn", filename);
        exit(1);
    }

    /* Retrieve file lenght. */
    if (fseek(fd_coefficients, 0, SEEK_END) != 0) {
        fprintf(stderr, "Error with Coefficients file\n");
        exit(1);
    }

    coeffs_file_len = ftell(fd_coefficients);
    if (coeffs_file_len < 0) {
        fprintf(stderr, "Error with Coefficients file: failed to get file length\n");
        exit(1);
    }

    /* Go back to the file begin */
    fseek(fd_coefficients, 0, SEEK_SET);

    /* convert size from Byte to word */
    coeffs_file_len /= 4;

    uint32_t coeffs[coeffs_file_len];
    int ret;
    ret = fread(coeffs, sizeof(uint32_t), coeffs_file_len, fd_coefficients);
    if (ret != coeffs_file_len) {
        fprintf(stderr, "Error with Coefficients file: failed to read %d -> %ld\n", ret, coeffs_file_len);
        exit(1);
    }

    /* Write coefficients */
    for (i = 0; i < coeffs_file_len; i++) {
        litepcie_writel(fd, CSR_FIR_DECIMATION_ADDR, i);
        litepcie_writel(fd, CSR_FIR_COEFF_WADDR_ADDR, coeffs[i]);
    }

    fclose(fd_coefficients);

    close(fd);
}

/* Help */
/*------*/

static void help(void)
{
    printf("LitePCIe utilities\n"
           "usage: litepcie_util [options] cmd [args...]\n"
           "\n"
           "options:\n"
           "-h                                Help.\n"
           "-c device_num                     Select the device (default = 0).\n"
           "\n"
           "available commands:\n"
           "coefficients filename             FIR Coefficients Configuration from file.\n"
           "\n"
           );
    exit(1);
}

/* Main */
/*------*/

int main(int argc, char **argv)
{
    const char *cmd;
    int c;

    litepcie_device_num = 0;

    /* Parameters. */
    for (;;) {
        c = getopt(argc, argv, "hc:f:");
        if (c == -1)
            break;
        switch(c) {
        case 'h':
            help();
            break;
        default:
            exit(1);
        }
    }

    /* Show help when too much args. */
    if (optind >= argc)
        help();

    /* Select device. */
    snprintf(litepcie_device, sizeof(litepcie_device), "/dev/litepcie%d", litepcie_device_num);

    cmd = argv[optind++];

    /* Fir Coefficients configuration */
    if (!strcmp(cmd, "coefficients")) {
        const char *filename = NULL;
        if (optind != argc) {
            goto show_help;
        }
        filename = argv[optind++];
        fir_coefficients_write(filename);
    }

    return 0;

show_help:
        help();

    return 0;
}
