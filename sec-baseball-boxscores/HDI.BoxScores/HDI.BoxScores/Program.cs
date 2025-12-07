using HDI.BoxScores.Configuration;
using HDI.BoxScores.Extensions;
using HDI.BoxScores.Services;
using Microsoft.Extensions.Configuration;
using Microsoft.Extensions.DependencyInjection;
using Microsoft.Extensions.Hosting;
using Serilog;

HostApplicationBuilder builder = Host.CreateApplicationBuilder(args);

builder.Services.AddSerilog(static (provider, config) => config.ReadFrom.Configuration(provider.GetRequiredService<IConfiguration>()));

builder.Services
    .AddOptions<BoxScoreOptions>()
    .BindConfiguration(BoxScoreOptions.SectionName)
    .ValidateDataAnnotations()
    .ValidateOnStart();

builder.Services.AddSheetsService();
builder.Services.AddChromeDriver();
builder.Services.AddHostedService<BoxScoreService>();

using IHost host = builder.Build();
await host.RunAsync();