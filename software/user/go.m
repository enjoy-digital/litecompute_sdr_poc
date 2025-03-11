close all;
clear all;

fd = fopen("toto.bin");
data = fread(fd, Inf, "int16");
dr = data(1:2:end);
di = data(2:2:end);

dd = dr + i * di;
plot(abs(dd))
