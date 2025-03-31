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
/*------------------*/

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
    printf("----------------------------------\n");

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
    int ret = fread(coeffs, sizeof(uint32_t), coeffs_file_len, fd_coefficients);
    if (ret != coeffs_file_len) {
        fprintf(stderr, "Error with Coefficients file: failed to read %d -> %ld\n", ret, coeffs_file_len);
        exit(1);
    }

    /* Write coefficients */
    for (i = 0; i < coeffs_file_len; i++) {
        litepcie_writel(fd, CSR_FIR_COEFF_WADDR_ADDR, i);
        litepcie_writel(fd, CSR_FIR_COEFF_WDATA_ADDR, coeffs[i]);
    }

    fclose(fd_coefficients);

    close(fd);
}

/* Fir Parameters configuration */
/*------------------------------*/

static void fir_configuration(uint32_t decimation, uint32_t operations, uint8_t odd_operations)
{
    int fd;

    printf("\e[1m[> Fir Parameters Configuration:\e[0m\n");
    printf("--------------------------------\n");

    fd = open(litepcie_device, O_RDWR);
    if (fd < 0) {
        fprintf(stderr, "Could not init driver %s\n", litepcie_device);
        exit(1);
    }

    /* write decimation. */
    litepcie_writel(fd, CSR_FIR_DECIMATION_ADDR, decimation);

    /* write operations (Minus one). */
    litepcie_writel(fd, CSR_FIR_OPERATIONS_MINUS_ONE_ADDR, operations - 1);

    /* write odd/event operations. */
    litepcie_writel(fd, CSR_FIR_CFG_ADDR, (odd_operations & 0x01) << CSR_FIR_CFG_ODD_OPERATIONS_OFFSET);

    close(fd);
}

/* Help */
/*------*/

static void help(void)
{
    printf("LitePCIe Fir Utility\n"
           "usage: litepcie_fir [options] cmd [args...]\n"
           "\n"
           "options:\n"
           "-h                    Help.\n"
           "-c device_num         Select the device (default = 0).\n"
           "-d decimation         Select decimation factor (default = 2).\n"
           "-o operations         Select number operations to performs (default = 4).\n"
           "-O odd_operations     Select if operations is odd or eveen (default = 0).\n"
           "\n"
           "available commands:\n"
           "coefficients filename FIR Coefficients Configuration from file.\n"
           "configuration         FIR Parameter Configuration.\n"
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
    uint32_t decimation = 2;
    uint32_t operations = 4;
    uint8_t odd_operations = 0;

    /* Parameters. */
    for (;;) {
        c = getopt(argc, argv, "hc:d:o:O:");
        if (c == -1)
            break;
        switch(c) {
        case 'h':
            help();
            break;
        case 'c':
            litepcie_device_num = atoi(optarg);
            break;
        case 'd':
            decimation = atoi(optarg);
            break;
        case 'o':
            operations = atoi(optarg);
            break;
        case 'O':
            odd_operations = atoi(optarg);
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

    /* Fir Coefficients configuration. */
    if (!strcmp(cmd, "coefficients")) {
        const char *filename = NULL;
        if (optind + 1 > argc) {
            goto show_help;
        }
        filename = argv[optind++];
        fir_coefficients_write(filename);
    /* Fir Parameters configuration. */
    } else if (!strcmp(cmd, "configuration")) {
        fir_configuration(decimation, operations, odd_operations);
    /* Show help otherwise. */
    } else
show_help:
        help();

    return 0;
}
