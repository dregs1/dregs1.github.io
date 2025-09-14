<?php
// Define o tipo de conteúdo como JSON.
header('Content-Type: application/json');

// O endereço de DNS que você quer usar.
$dns_address = "http://repi.live:8080/c/";

// Cria um array associativo para a resposta.
// Use "url" como a chave se for o que o aplicativo espera.
$response = array("url" => $dns_address);

// Converte o array em uma string JSON e a imprime.
echo json_encode($response);
?>
